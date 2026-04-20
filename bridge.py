from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd

def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet
    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]

def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
    """
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return

    # 1. Setup Connections and Contracts
    w3_source = connect_to('source')
    w3_dest = connect_to('destination')
    
    # YOUR PRIVATE KEY HERE - Required to sign the cross-chain transactions
    private_key = "YOUR_PRIVATE_KEY_HERE"
    account = w3_source.eth.account.from_key(private_key)
    
    source_info = get_contract_info('source', contract_info)
    dest_info = get_contract_info('destination', contract_info)
    
    source_contract = w3_source.eth.contract(address=source_info['address'], abi=source_info['abi'])
    dest_contract = w3_dest.eth.contract(address=dest_info['address'], abi=dest_info['abi'])

    # 2. Logic for scanning the Source chain (Avalanche)
    if chain == 'source':
        start_block = w3_source.eth.block_number - 5
        print(f"Scanning Source (Avalanche) for Deposit events from block {start_block}...")
        
        # Create filter for Deposit events
        deposit_filter = source_contract.events.Deposit.create_filter(fromBlock=start_block, toBlock='latest')
        events = deposit_filter.get_all_entries()
        
        for event in events:
            token = event.args.token
            recipient = event.args.recipient
            amount = event.args.amount
            print(f"Detected Deposit: {amount} of {token} for {recipient}")
            
            # Execute wrap() on Destination (BSC)
            nonce = w3_dest.eth.get_transaction_count(account.address)
            tx = dest_contract.functions.wrap(token, recipient, amount).build_transaction({
                'chainId': 97, # BSC Testnet Chain ID
                'gas': 3000000,
                'gasPrice': w3_dest.eth.gas_price,
                'nonce': nonce,
            })
            signed_tx = w3_dest.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3_dest.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Sent wrap() transaction to BSC. Hash: {tx_hash.hex()}")
            w3_dest.eth.wait_for_transaction_receipt(tx_hash)

    # 3. Logic for scanning the Destination chain (BSC)
    if chain == 'destination':
        start_block = w3_dest.eth.block_number - 5
        print(f"Scanning Destination (BSC) for Unwrap events from block {start_block}...")
        
        # Create filter for Unwrap events
        unwrap_filter = dest_contract.events.Unwrap.create_filter(fromBlock=start_block, toBlock='latest')
        events = unwrap_filter.get_all_entries()
        
        for event in events:
            underlying_token = event.args.underlying_token
            recipient = event.args.to  # The parameter name in your Solidity event is 'to'
            amount = event.args.amount
            print(f"Detected Unwrap: {amount} of {underlying_token} for {recipient}")
            
            # Execute withdraw() on Source (Avalanche)
            nonce = w3_source.eth.get_transaction_count(account.address)
            tx = source_contract.functions.withdraw(underlying_token, recipient, amount).build_transaction({
                'chainId': 43113, # Avalanche Fuji Testnet Chain ID
                'gas': 3000000,
                'gasPrice': w3_source.eth.gas_price,
                'nonce': nonce,
            })
            signed_tx = w3_source.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3_source.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Sent withdraw() transaction to Avalanche. Hash: {tx_hash.hex()}")
            w3_source.eth.wait_for_transaction_receipt(tx_hash)
