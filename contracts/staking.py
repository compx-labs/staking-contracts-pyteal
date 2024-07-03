from pyteal import *
import os
import json

token_id = Bytes("tid")
reward_id = Bytes("rid")
slope_start = Bytes("ss")
slope_end = Bytes("se")
length_start = Bytes("ls")
length_end = Bytes("le")
freeze_flag = Bytes("f")
locked = Bytes("l")
total_liability = Bytes("tl")
staked = Bytes("s")
total_reward = Bytes("tr")
stake_unlock = Bytes("su")

scratch_rate = ScratchVar(TealType.uint64)
scratch_out = ScratchVar(TealType.uint64)
scratch_stakePrice = ScratchVar(TealType.uint64)
scratch_rewardPrice = ScratchVar(TealType.uint64)


@Subroutine(TealType.none)
def admin_check() -> Expr:
    return Assert(Txn.sender() == App.globalGet(Bytes("a")))


@Subroutine(TealType.uint64)
def interest_rate(length: abi.Uint64) -> Expr:
    rate = App.globalGet(slope_start) + ((length.get() - App.globalGet(length_start)) *
                                          (Int(1_000_000) * (App.globalGet(slope_end) - App.globalGet(slope_start))) /
                                          (App.globalGet(length_end) - App.globalGet(length_start))) / Int(1_000_000)
    # Adjust APR to rate over the given length
    return (length.get() * Int(1_000_000)) / Int(365) * rate / Int(1_000_000)

@Subroutine(TealType.uint64)
def get_asset_price(folks_feed_oracle: abi.Application, asa_id: abi.Asset):
    asa_info = App.globalGetEx(folks_feed_oracle.application_id(), Itob(asa_id.asset_id()))
    return Seq(asa_info, Assert(asa_info.hasValue()), ExtractUint64(asa_info.value(), Int(0)))



optin = Seq(
    # Staked
    App.localPut(Txn.sender(), staked, Int(0)),
    # Total reward
    App.localPut(Txn.sender(), total_reward, Int(0)),
    # Stake unlock
    App.localPut(Txn.sender(), stake_unlock, Int(0)),
    Approve()
)

router = Router(
    name="Staking",
    bare_calls=BareCallActions(
        opt_in=OnCompleteAction(action=optin, call_config=CallConfig.CALL),
        update_application=OnCompleteAction(action=admin_check, call_config=CallConfig.CALL),
    )
)


# Router methods
@router.method(no_op=CallConfig.CREATE)
def create(token: abi.Asset, ss: abi.Uint64, se: abi.Uint64, ls: abi.Uint64, le: abi.Uint64, reward: abi.Asset) -> Expr:
    logic = Seq(
        # Set admin
        App.globalPut(Bytes("a"), Txn.sender()),
        # Staking Token
        App.globalPut(token_id, token.asset_id()),
        # Reward Token
        App.globalPut(reward_id, reward.asset_id()),
        # Freeze flag | if set to 1 then the contract is frozen
        App.globalPut(freeze_flag, Int(1)),
        # Slope start
        App.globalPut(slope_start, ss.get()),
        # Slope end
        App.globalPut(slope_end, se.get()),
        # Length start
        App.globalPut(length_start, ls.get()),
        # Length end
        App.globalPut(length_end, le.get()),
        # Locked | How much of the ASA is locked (owned by user)
        App.globalPut(locked, Int(1)),
        # Total liability | How much the contract owes to stakers
        App.globalPut(total_liability, Int(0)),
        # Approve
        Approve()
    )

    return Seq(
        logic,
        Approve(),
    )


@router.method(no_op=CallConfig.CALL)
def config(token: abi.Asset, reward: abi.Asset):
    """
    ADMIN Function
    Used to configure params in contract and do opt-ins
    Fee: 2
    """
    validation = And(
        Gtxn[Txn.group_index() - Int(1)].type_enum() == TxnType.Payment,
        Gtxn[Txn.group_index() - Int(1)].sender() == Txn.sender(),
        Gtxn[Txn.group_index() - Int(1)].receiver() == Global.current_application_address(),
        Gtxn[Txn.group_index() - Int(1)].amount() == Int(200_000),
        # Verify correct token id
        App.globalGet(token_id) == token.asset_id(),
        App.globalGet(reward_id) == reward.asset_id(),
    )

    logic = Seq(
        # Opt-in to token
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: token.asset_id(),
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
            TxnField.fee: Int(0),
        }),
        InnerTxnBuilder.Submit(),
        
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: reward.asset_id(),
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
            TxnField.fee: Int(0),
        }),
        InnerTxnBuilder.Submit(),

        # Unfreeze contract
        App.globalPut(freeze_flag, Int(0)),
    )

    return Seq(
        admin_check(),
        Assert(validation),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def update_admin(addr: abi.Account) -> Expr:
    """
    ADMIN Function
    Update Admin Address
    """
    logic = Seq(
        # Set admin
        App.globalPut(Bytes("a"), addr.address()),
    )

    return Seq(
        admin_check(),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def update_settings(ss: abi.Uint64, se: abi.Uint64, ls: abi.Uint64, le: abi.Uint64) -> Expr:
    """
    ADMIN Function
    Update staking variables
    """

    logic = Seq(
        # Update ss, se, ls and le
        App.globalPut(slope_start, ss.get()),
        App.globalPut(slope_end, se.get()),
        App.globalPut(length_start, ls.get()),
        App.globalPut(length_end, le.get()),
    )

    return Seq(
        admin_check(),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def withdraw(asset: abi.Asset, amount: abi.Uint64) -> Expr:
    """
    ADMIN Function
    Used to withdraw Algo or ASA from the contract, to withdraw ALGO, asset should be 1
    Fee: 2
    """

    logic = Seq(
        InnerTxnBuilder.Begin(),
        If(  # If ALGO
            asset.asset_id() == Int(1),
        ).Then(
            # Send to admin
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: Txn.sender(),
                TxnField.amount: amount.get(),
                TxnField.fee: Int(0),
            }),
        ).Else(
            # Validate there is enough token with locked value
            balance := AssetHolding.balance(Global.current_application_address(), asset.asset_id()),
            Assert(balance.hasValue()),
            # Verify free token is greater or equal to amount
            Assert(Gt(balance.value() - App.globalGet(locked) - App.globalGet(total_liability), amount.get())),
            # Send to admin
            InnerTxnBuilder.SetFields({
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: asset.asset_id(),
                TxnField.asset_receiver: Txn.sender(),
                TxnField.asset_amount: amount.get(),
                TxnField.fee: Int(0),
            }),
        ),
        InnerTxnBuilder.Submit(),
        # Need to add reward asset possibly
    )

    return Seq(
        admin_check(),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def stake(asset: abi.Asset, length: abi.Uint64) -> Expr:
    """
    Used to stake tokens
    Fee: 1
    """
    validation = And(
        # Verify ASA Tx
        Gtxn[Txn.group_index() - Int(1)].type_enum() == TxnType.AssetTransfer,
        Gtxn[Txn.group_index() - Int(1)].sender() == Txn.sender(),
        Gtxn[Txn.group_index() - Int(1)].asset_receiver() == Global.current_application_address(),
        Gtxn[Txn.group_index() - Int(1)].asset_amount() > Int(0),
        Gtxn[Txn.group_index() - Int(1)].xfer_asset() == asset.asset_id(),
        # Verify correct token id
        App.globalGet(token_id) == asset.asset_id(),
        # Verify correct length
        And(
            length.get() >= App.globalGet(length_start),
            length.get() <= App.globalGet(length_end),
        ),
        # Verify there is no current stake
        App.localGet(Txn.sender(), staked) == Int(0),
        # Frozen check
        App.globalGet(freeze_flag) == Int(0),
    )

    logic = Seq(
        # Calculate interest rate using linear slope from start to end
        scratch_rate.store(
            interest_rate(length)
        ),
        scratch_stakePrice.store(get_asset_price(159512493, asset)),
        scratch_rewardPrice.store(get_asset_price(159512493, App.globalGet(reward_id))),
        # DEBUG store scratch_rate
        App.globalPut(Bytes("RATE"), scratch_rate.load()), #DEBUGDEBUGDEBUGDEBUGDEBUGDEBUGDEBUG
        # Calculate output
        scratch_out.store(
            ((Gtxn[Txn.group_index() - Int(1)].asset_amount() * scratch_stakePrice.load() * (Int(1_000_000) + scratch_rate.load())) / scratch_rewardPrice.load()) / Int(1_000_000)
        ),# (stakedAmount * staked_asset_price)  * rate 
        # Set staked amount
        App.localPut(Txn.sender(), staked, Gtxn[Txn.group_index() - Int(1)].asset_amount()),
        # Set reward
        App.localPut(Txn.sender(), total_reward, scratch_out.load() - Gtxn[Txn.group_index() - Int(1)].asset_amount()),
        # Set stake_unlock
        App.localPut(Txn.sender(), stake_unlock, Global.latest_timestamp() + (length.get() * Int(86400))), 
        # Update global locked
        App.globalPut(locked, App.globalGet(locked) + App.localGet(Txn.sender(), staked)),
        # Update global liability
        App.globalPut(total_liability, App.globalGet(total_liability) + App.localGet(Txn.sender(), total_reward)),

    )

    return Seq(
        Assert(validation),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def unstake(asset: abi.Asset, reward: abi.Asset) -> Expr:
    """
    Used to unstake tokens
    Fee: 2
    """
    validation = And(
        # Verify correct token id
        App.globalGet(token_id) == asset.asset_id(),
        # Verify correct reward id
        App.globalGet(reward_id) == reward.asset_id(),
        # Verify there is a current stake
        App.localGet(Txn.sender(), staked) > Int(0),
        # Verify time is up
        Global.latest_timestamp() > App.localGet(Txn.sender(), stake_unlock),
    )

    logic = Seq(
        # Send tokens to user
        InnerTxnBuilder.Begin(),
        
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: asset.asset_id(),
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: App.localGet(Txn.sender(), staked),
            TxnField.fee: Int(0),
        }),
    
        InnerTxnBuilder.Next(), 
        
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: asset.asset_id(),
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: App.localGet(Txn.sender(), total_reward),
            TxnField.fee: Int(0),
        }),
        
        InnerTxnBuilder.Submit(),
        
        # Subtract staked amount from global locked
        App.globalPut(locked, App.globalGet(locked) - App.localGet(Txn.sender(), staked)),
        # Subtract reward from global liability
        App.globalPut(total_liability, App.globalGet(total_liability) - App.localGet(Txn.sender(), staked)),
        # Set staked amount to 0
        App.localPut(Txn.sender(), staked, Int(0)),
        # Set reward to 0
        App.localPut(Txn.sender(), total_reward, Int(0)),
        # Set stake_unlock to 0
        App.localPut(Txn.sender(), stake_unlock, Int(0)),
    )

    return Seq(
        Assert(validation),
        logic,
        Approve()
    )


@router.method(no_op=CallConfig.CALL)
def restake(asset: abi.Asset, length: abi.Uint64) -> Expr:
    """
    Used to restake tokens
    Fee: 1
    """
    validation = And(
        # Verify correct token id
        App.globalGet(token_id) == asset.asset_id(),
        # Verify correct length
        And(
            length.get() >= App.globalGet(length_start),
            length.get() <= App.globalGet(length_end),
        ),
        # Verify there is a current stake
        App.localGet(Txn.sender(), staked) > Int(0),
        # Verify time is up
        Global.latest_timestamp() > App.localGet(Txn.sender(), stake_unlock),
        # Frozen check
        App.globalGet(freeze_flag) == Int(0),
    )

    logic = Seq(
        # Calculate interest rate using linear slope from start to end
        scratch_rate.store(
            interest_rate(length)
        ),
        # DEBUG store scratch_rate
        App.globalPut(Bytes("RATE"), scratch_rate.load()), #DEBUGDEBUGDEBUGDEBUGDEBUGDEBUGDEBUG
        # Calculate output
        scratch_out.store(
            WideRatio(
                [App.localGet(Txn.sender(), staked) + App.localGet(Txn.sender(), total_reward), Int(1_000_000) + scratch_rate.load()],
                [Int(1_000_000)]
            )
        ),
        # Reduce global locked
        App.globalPut(locked, App.globalGet(locked) - App.localGet(Txn.sender(), staked)),
        # Reduce global liability
        App.globalPut(total_liability, App.globalGet(total_liability) - App.localGet(Txn.sender(), total_reward)),
        # Set staked amount
        App.localPut(Txn.sender(), staked, App.localGet(Txn.sender(), staked) + App.localGet(Txn.sender(), total_reward)),
        # Set reward
        App.localPut(Txn.sender(), total_reward, scratch_out.load() - App.localGet(Txn.sender(), staked)),
        # Set stake_unlock
        App.localPut(Txn.sender(), stake_unlock, Global.latest_timestamp() + (length.get() * Int(86400) * Int(0))), #DEBUGDEBUGDEBUGDEBUGDEBUGDEBUGDEBUG
        # Update global locked
        App.globalPut(locked, App.globalGet(locked) + App.localGet(Txn.sender(), staked)),
        # Update global liability
        App.globalPut(total_liability, App.globalGet(total_liability) + App.localGet(Txn.sender(), total_reward)),

    )

    return Seq(
        Assert(validation),
        logic,
        Approve()
    )


# Compile
if __name__ == "__main__":
    approval_program, clear_state_program, contract = router.compile_program(
        version=7, optimize=OptimizeOptions(scratch_slots=True)
    )

    approval_path = f"../build2/{router.name}/approval.teal"
    clear_path = f"../build2/{router.name}/clear.teal"
    abi_path = f"../build2/{router.name}/abi.json"

    if os.path.exists(approval_path):
        os.remove(approval_path)

    if os.path.exists(clear_path):
        os.remove(clear_path)

    with open(approval_path, "w") as f:
        f.write(approval_program)

    with open(clear_path, "w") as f:
        f.write(clear_state_program)

    with open(abi_path, "w") as f:
        f.write(json.dumps(contract.dictify(), indent=4))
