from deploy.utils import Interface
from dotenv import dotenv_values
from algosdk import account, encoding, mnemonic
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner, AccountTransactionSigner
from algosdk.abi import Contract
from algosdk.error import AlgodHTTPError
from algosdk.transaction import (StateSchema, ApplicationOptInTxn, ApplicationCallTxn, ApplicationCreateTxn, PaymentTxn,
                                        AssetCreateTxn, OnComplete)

ENABLED = False

contract = {
    "Staking": 0
}

assets = {
    "GATOR": 0000,
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
approval, clear = interface.program("Staking")
with open("../../build/Staking/abi.json") as f:
    abi = f.read()
staking_contract = Contract.from_json(abi)

gtx = AtomicTransactionComposer()
gtx.add_method_call(
    app_id=contract['Staking'],
    on_complete=OnComplete.NoOpOC,
    method=staking_contract.get_method_by_name("update_admin"),
    sender=creator,
    sp=interface.get_suggested_params(),
    signer=creator_signer,
    method_args=[
        "ADDRESS",
    ]
)
tx_id = gtx.submit(interface.algod)
resp = interface.wait_for_confirmation(tx_id[0])
print("Updated admin address")



