class MCPServers:
    mcp_servers = None

    def __init__(self, mcp_servers=[]):
        self.mcp_servers = mcp_servers


    def add_server(self, server_name:str,server_address:str,server_functions:list[str]):
        """
            入参：server_name="百度搜索",server_address="127.0.0.1:8080",server_function=[web_search]
        """
        server = {
            'server_name': server_name,
            'server_address': server_address,
            'server_functions': server_functions,
        }
        self.mcp_servers.append(server)

    def get_servers(self):
        return self.mcp_servers