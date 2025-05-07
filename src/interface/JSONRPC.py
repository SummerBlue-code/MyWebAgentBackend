import json
from typing import Optional

import requests


class JSONRPC:
    id = None
    method_name:str = None
    params:Optional[list|dict] = None
    jsonrpc_version:str = None
    result:Optional[dict] = None

    def __init__(self, id, method_name, params, jsonrpc_version="2.0"):
        self.id = id
        self.method_name = method_name
        self.params = params
        self.jsonrpc_version = jsonrpc_version


    def _get_data(self):
        return {
            "method": self.method_name,
            "params": self.params,
            "jsonrpc": self.jsonrpc_version,
            "id": self.id,
        }

    def request_data(self,server_address):
        data = requests.request("POST", url=server_address,json=self._get_data()).json()
        self.result = json.load(data)
        return self

    def get_result(self):
        return self.result