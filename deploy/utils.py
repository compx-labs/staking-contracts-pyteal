import os
from base64 import b64decode
from algosdk.v2client.algod import AlgodClient
from algosdk import account, mnemonic


class Interface:
    def __init__(self, token, address):
        self.algod = AlgodClient(token, address)

        print(self.algod.status())

    def get_suggested_params(self, fee=1):
        suggested_params = self.algod.suggested_params()
        suggested_params.flat_fee = True
        suggested_params.fee = suggested_params.min_fee * fee
        return suggested_params

    def program(self, name):
        with open(f"../../build/{name}/approval.teal", "r") as file:
            approval = self.algod.compile(file.read())["result"]
        with open(f"../../build/{name}/clear.teal", "r") as file:
            clear = self.algod.compile(file.read())["result"]

        return b64decode(approval), b64decode(clear)

    def wait_for_confirmation(self, txid):
        last_round = self.algod.status().get("last-round")
        txinfo = self.algod.pending_transaction_info(txid)
        while not (txinfo.get("confirmed-round") and txinfo.get("confirmed-round") > 0):
            print("Waiting for confirmation")
            last_round += 1
            self.algod.status_after_block(last_round)
            txinfo = self.algod.pending_transaction_info(txid)
        txinfo["txid"] = txid
        return txinfo


# Generate 3 accounts(creator, user, vault) and store mnemonic in .env
def generate_accounts():
    creator_sk, creator_pk = account.generate_account()
    creator_mnemonic = mnemonic.from_private_key(creator_sk)
    print(f"Creator: {creator_pk}")

    user_sk, user_pk = account.generate_account()
    user_mnemonic = mnemonic.from_private_key(user_sk)
    print(f"User: {user_pk}")

    # Create new .env file
    with open(".env", "w") as file:
        file.write(f'creator="{creator_mnemonic}"\n')
        file.write(f'user="{user_mnemonic}"\n')


if __name__ == "__main__":
    generate_accounts()