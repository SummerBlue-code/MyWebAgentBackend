from abc import abstractmethod
from http.server import BaseHTTPRequestHandler


class MCPServer():
    @abstractmethod
    def tools(self):
        pass
