from deploy.utils import Interface
from dotenv import dotenv_values
from algosdk import account, encoding, mnemonic
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner, AccountTransactionSigner
from algosdk.abi import Contract
from algosdk.error import AlgodHTTPError
from algosdk.transaction import (StateSchema, ApplicationOptInTxn, ApplicationCallTxn, ApplicationCreateTxn, PaymentTxn,
                                        AssetCreateTxn, OnComplete)

ENABLED = True

contract = {}

assets = {
    "XUSD": 212014591,
    "PRIV": 212014630,
}

# Load wallets
env_vars = dotenv_values("../.env")
creator_sk = mnemonic.to_private_key(env_vars["creator"])
creator = account.address_from_private_key(creator_sk)
creator_signer = AccountTransactionSigner(creator_sk)
print(f"Creator: {creator}")

# Create Interface
interface = Interface(
    "",
    "https://testnet-api.algonode.cloud"
)

# If ENABLED is False, stop the script
if not ENABLED:
    print("Script is disabled")
    exit()

# Deploy Staking Contract
approval, clear = interface.program("Staking")
with open("../../build/Staking/abi.json") as f:
    abi = f.read()
staking_contract = Contract.from_json(abi)

gtx = AtomicTransactionComposer()
gtx.add_method_call(
    app_id=0,
    on_complete=OnComplete.NoOpOC,
    method=staking_contract.get_method_by_name("create"),
    sender=creator,
    sp=interface.get_suggested_params(1),
    signer=creator_signer,
    method_args=[
        assets["XUSD"], 50_000, 150_000, 15, 60
    ],
    approval_program=approval,
    clear_program=clear,
    global_schema=StateSchema(num_byte_slices=1, num_uints=9),
    local_schema=StateSchema(num_byte_slices=0, num_uints=3),
    extra_pages=0,
)
tx_id = gtx.submit(interface.algod)
resp = interface.wait_for_confirmation(tx_id[0])
contract['Staking'] = resp['application-index']
staking_addr = get_application_address(contract['Staking'])
print(f"Created Staking app with ID {contract['Staking']}")
print(f"Staking App address is {staking_addr}")

# Config Staking app
gtx = AtomicTransactionComposer()
gtx.add_transaction(
    TransactionWithSigner(
        PaymentTxn(
            sender=creator,
            sp=interface.get_suggested_params(),
            receiver=staking_addr,
            amt=200_000,
        ),
        creator_signer)
)
gtx.add_method_call(
    app_id=contract['Staking'],
    on_complete=OnComplete.NoOpOC,
    method=staking_contract.get_method_by_name("config"),
    sender=creator,
    sp=interface.get_suggested_params(2),
    signer=creator_signer,
    method_args=[
        assets["XUSD"],
    ],
)
tx_id = gtx.submit(interface.algod)
print("Config Staking app")