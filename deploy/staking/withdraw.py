from deploy.utils import Interface
from dotenv import dotenv_values
from algosdk import account, encoding, mnemonic
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner, AccountTransactionSigner
from algosdk.abi import Contract
from algosdk.error import AlgodHTTPError
from algosdk.transaction import (StateSchema, ApplicationOptInTxn, ApplicationCallTxn, ApplicationCreateTxn, PaymentTxn,
                                        AssetCreateTxn, AssetTransferTxn, OnComplete)

ENABLED = False

contract = {
    "Staking": 0000
}

assets = {
    "ALGO": 1,
    "XUSD": 0000,
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

# IDO Contract
approval, clear = interface.program("IDO")
with open("../../build/Staking/abi.json") as f:
    abi = f.read()
staking_contract = Contract.from_json(abi)
staking_addr = get_application_address(contract['IDO'])

# Withdraw
gtx = AtomicTransactionComposer()
gtx.add_method_call(
    app_id=contract['Staking'],
    on_complete=OnComplete.NoOpOC,
    method=staking_contract.get_method_by_name("withdraw"),
    sender=creator,
    sp=interface.get_suggested_params(),
    signer=creator_signer,
    method_args=[
        assets["XUSD"],
        0,
    ]
)
tx_id = gtx.submit(interface.algod)
print("Withdraw Staking")

