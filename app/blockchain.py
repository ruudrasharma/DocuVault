
import hashlib
import json
from time import time
import os

class Block:
    def __init__(self, index, previous_hash, timestamp, data, hash):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = timestamp
        self.data = data
        self.hash = hash

class Blockchain:
    def __init__(self):
        os.makedirs('blockchain_data', exist_ok=True)
        self.chain = []
        try:
            with open('blockchain_data/chain.json', 'r') as f:
                chain_data = json.load(f)
                self.chain = [Block(b['index'], b['previous_hash'], b['timestamp'], b['data'], b['hash']) for b in chain_data]
            if not self.chain:  # Ensure genesis block if chain is empty
                self.chain = [self.create_genesis_block()]
                self.save_chain()
        except (FileNotFoundError, json.JSONDecodeError):
            self.chain = [self.create_genesis_block()]
            self.save_chain()

    def create_genesis_block(self):
        genesis = Block(0, '0', time(), 'Genesis', self.calculate_hash(0, '0', time(), 'Genesis'))
        return genesis

    def calculate_hash(self, index, previous_hash, timestamp, data):
        return hashlib.sha256(f"{index}{previous_hash}{timestamp}{data}".encode()).hexdigest()

    def add_block(self, data):
        previous_block = self.chain[-1]
        new_index = previous_block.index + 1
        new_timestamp = time()
        new_hash = self.calculate_hash(new_index, previous_block.hash, new_timestamp, data)
        new_block = Block(new_index, previous_block.hash, new_timestamp, data, new_hash)
        self.chain.append(new_block)
        self.save_chain()

    def is_valid_hash(self, cert_hash):
        return any(block.data == cert_hash for block in self.chain)

    def save_chain(self):
        try:
            with open('blockchain_data/chain.json', 'w') as f:
                json.dump([{
                    'index': b.index,
                    'previous_hash': b.previous_hash,
                    'timestamp': b.timestamp,
                    'data': b.data,
                    'hash': b.hash
                } for b in self.chain], f)
        except Exception as e:
            print(f"Error saving blockchain: {e}")

blockchain = Blockchain()
