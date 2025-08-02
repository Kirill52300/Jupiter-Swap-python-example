import aiohttp
from solders import message
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from base64 import b64encode, b64decode
from solana.rpc.async_api import AsyncClient
from spl.token.instructions import get_associated_token_address
from spl.token.constants import TOKEN_PROGRAM_ID
from solders.signature import Signature

class JupSwap:
    def __init__(
        self,
        private_key_str: str = None,
        rpc_url: str = None
    ):
        if private_key_str is None:
            return "Private key is required"
        if rpc_url is None:
            rpc_url = "https://api.mainnet-beta.solana.com/"
       
        # if rpc_url is None:
        #     rpc_url = "https://api.mainnet-beta.solana.com/"
        self.private_key = Keypair.from_base58_string(private_key_str)
        self.rpc_url = rpc_url

    async def fetch_and_execute(
        self,
        inputMint: str,
        outputMint: str,
        amount: int,
        slippageBps: int = 300,
        priorityFeeLamports: int = 500000
    ):
        url = (
            "https://ultra-api.jup.ag/order"
            f"?inputMint={inputMint}"
            f"&outputMint={outputMint}"
            f"&amount={amount}"
            "&swapMode=ExactIn"
            f"&slippageBps={slippageBps}"
            "&broadcastFeeType=maxCap"
            f"&priorityFeeLamports={priorityFeeLamports}"
            "&useWsol=false"
            "&asLegacyTransaction=false"
            "&excludeDexes="
            "&excludeRouters="
            "&taker=zswtZ86iSzSzmeDtQtEKX7WSHVcNDPkCTHDD1uMMbue"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                transaction_b64 = data.get("transaction")
                request_id = data.get("requestId")
                if not transaction_b64 or not request_id:
                    msg = "Такая транзакция недоступна, проверьте баланс"
                    return msg

                raw_transaction = VersionedTransaction.from_bytes(b64decode(transaction_b64))
                signature = self.private_key.sign_message(message.to_bytes_versioned(raw_transaction.message))
                signed_txn = VersionedTransaction.populate(raw_transaction.message, [signature])
                execute_url = "https://ultra-api.jup.ag/execute"
                signed_txn_b64 = b64encode(bytes(signed_txn)).decode("utf-8")
                payload = {
                    "requestId": request_id,
                    "signedTransaction": signed_txn_b64
                }
                async with session.post(execute_url, json=payload, headers=headers) as resp:
                    result = await resp.json()
                    print(result)
                    if result.get("status") == "Success":
                        msg = f"Succes: {result.get('signature')}"
                        msg += f"\nhttps://explorer.solana.com/tx/{result.get('signature')}"
                        msg += f"\nhttps://ultra-api.jup.ag/tx/{result.get('signature')}"
                        return msg
                    else:
                        msg = f"Fail: {result.get('error', result)}"
                        msg += f"\nhttps://explorer.solana.com/tx/{result.get('signature') if result.get('signature') else 'unknown'}"
                        msg += f"\nhttps://ultra-api.jup.ag/tx/{result.get('signature') if result.get('signature') else 'unknown'}"
                        return msg

    async def get_balance(self):
        client = AsyncClient(self.rpc_url)
        resp = await client.get_balance(self.private_key.pubkey())
        await client.close()
        return resp
    async def get_token_balance(self, pubkey: str):
        client = AsyncClient(self.rpc_url)
        pubkey_owner =self.private_key.pubkey()
        
      
        if  pubkey=='So11111111111111111111111111111111111111112':
            balance = await self.get_balance()
            return balance
        resp_token =  get_associated_token_address(pubkey_owner,Pubkey.from_string(pubkey))
        resp = await client.get_token_account_balance(resp_token)
        await client.close()
        return resp
     #   return None


def extract_received_amount(txn_result, mint):
    """
    Get how many tokens of mint were received in the transaction.
    txn_result — result of client.get_transaction(...)
    mint — mint token string
    """
    meta = None
    if isinstance(txn_result, dict):
        meta = txn_result.get("result", {}).get("meta")
    elif hasattr(txn_result, "value"):
        meta = getattr(txn_result.value, "meta", None)
    if not meta:
        return None

    pre = None
    post = None
    # For JSON response
    pre_token_balances = meta.get("preTokenBalances") or meta.get("pre_token_balances")
    post_token_balances = meta.get("postTokenBalances") or meta.get("post_token_balances")
    if pre_token_balances and post_token_balances:
        for bal in pre_token_balances:
            if bal.get("mint") == mint:
                pre = int(bal["uiTokenAmount"]["amount"])
        for bal in post_token_balances:
            if bal.get("mint") == mint:
                post = int(bal["uiTokenAmount"]["amount"])
    if pre is not None and post is not None:
        return post - pre
    return None

# Example usage:
# if __name__ == "__main__":
#     import asyncio
#
#     # You can skip parameters, default values will be used
#     swap = JupSwap(private_key_str='2iVCnkWss6sM9FazYQnvRNWq3U59GinMVKWKXvSNUPhud5mLVdCuafeqz6mw1aeNDtDYVTu3jytrDveKyeyizBR6')
#
#     async def main():
#         # Example swap
#         balance = await swap.get_token_balance('So11111111111111111111111111111111111111112')
#         if hasattr(balance.value,'amount'):
#             result = await swap.fetch_and_execute(
#                 inputMint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # So11111111111111111111111111111111111111112
#                 outputMint="So11111111111111111111111111111111111111112", # EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
#                 amount=int(balance.value.amount)-500000
#             )
#             print(result)
#         else:
#             result = await swap.fetch_and_execute(
#                 inputMint="So11111111111111111111111111111111111111112", # So11111111111111111111111111111111111111112
#                 outputMint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
#                 amount=int(balance.value)-500000*10
#             )
#
#             # Get transaction JSON object
#
#             # Get how many EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v tokens were received
#
#         # Example of getting balance
#         # balance = await swap.get_balance()
#         # print(f"Balance  {balance}")
#         # print(f'Balance in Solana: {balance.value/  1_000_000_000}')
#
#     asyncio.run(main())

