from http.server import BaseHTTPRequestHandler
from jsonrpcserver import method, serve, Success, dispatch



@method(name='execute_python_code')
def _execute_python_code(code: str, timeout=10, allowed_modules=None):
    response = execute_python_code(code, timeout, allowed_modules)
    return Success(response)

class MojiWeatherHttpServer(BaseHTTPRequestHandler):
    def do_POST(self):
        # Process request
        request = self.rfile.read(int(self.headers["Content-Length"])).decode()
        response = dispatch(request)

        # Return response
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(response.encode())