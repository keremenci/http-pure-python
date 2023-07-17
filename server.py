import os
import socket
import mimetypes
from math import sqrt
import logging
import json

BLANK_LINE = b'\r\n'

class TCPServer:
    """Base server class for handling TCP connections. 
    The HTTP server will inherit from this class.
    """

    def __init__(self, host='127.0.0.1', port=8080):
        self.host = host
        self.port = port
        
    def recvall(self, sock): # imagine doing socket programming in 2022
        BUFF_SIZE = 4096 # 4 KiB
        fragments = []
        sock.settimeout(1)
        while True: 
            try:
                chunk = sock.recv(BUFF_SIZE)
            except TimeoutError:
                chunk = None
            if not chunk:
                break
            fragments.append(chunk)
        data = b''.join(fragments)
        return data

    def start(self):
        """Method for starting the server"""

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(5)

        print("Listening at", s.getsockname())

        while True:
            conn, addr = s.accept()
            print("Connected by", addr)
            
            # For the sake of this tutorial, 
            # we're reading just the first 1024 bytes sent by the client.
            data = self.recvall(conn)
            try:
                response = self.handle_request(data)
                conn.sendall(response)
                conn.close()
            except Exception:
                import traceback
                print(traceback.format_exc())


    def handle_request(self, data):
        """Handles incoming data and returns a response.
        Override this in subclass.
        """
        return data
    

class HTTPRequest:
    """Parser for HTTP requests. 
    It takes raw data and extracts meaningful information about the incoming request.
    """

    def __init__(self, data):
        self.method = None
        self.endpoint = None
        self.qparams = None
        self.http_version = None
        self.headers = None
        self.body = None

        # call self.parse method to parse the request data
        self.doParse(data)

    def doParse(self, data):
        head, self.body = data.split(b'\r\n\r\n', 1)
        headerlines = iter(head.decode().split('\r\n'))
        print(head)

        request_line = next(headerlines) # request line is the first line of the data
        
        words = request_line.split(' ') # split request line into seperate words

        self.method = words[0] # call decode to convert bytes to string
        
        uri = next(v.strip('/') for v in words if v.startswith('/'))
        if '?' in uri:
            self.endpoint, rest = uri.split('?', 1)
            self.qparams = {k:v for k, v in [p.split('=',1) for p in rest.split('&')]}
        else:
            self.endpoint = uri
            self.qparams = None
        try: 
            self.http_version = next(v for v in words if v.startswith('HTTP'))[5:]
        except StopIteration:
            self.http_version = '1.1' # Default to 1.1 if client does not provide version
        self.headers = {k:v for k,v in [line.split(': ', 1) for line in [*headerlines]]}
        
        print(f"""
        {self.method=}
        {self.endpoint=}
        {self.qparams=}
        {self.http_version=}
        {self.headers=}
        """#{self.body=}
        #"""
        )
        

class FormData:
    def __init__(self, data: bytes, boundary: bytes):
        self.boundary = boundary
        self.headers = None
        self.formbody = None
        
        self.doParse(data)
        
    def doParse(self, data: bytes):
        form_parts = data.split(b'--' + self.boundary)[1:-1] # there is a -- remaining in the last element
        for part in form_parts:
            tmpheaders, self.formbody = part.split(b'\r\n\r\n', 1)
            self.headers = {k.decode():v.decode() for k,v in [header.split(b': ') for header in tmpheaders.split(b'\r\n')[1:]]}
        

class HTTPServer(TCPServer):
    """The actual HTTP server class."""
    def __init__(self):
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s : %(levelname)s : %(name)s : %(message)s')
        self.logger = logging.getLogger(__name__)
        
        self.headers = {
            'Server': 'KeremenciServer',
            'Content-Type': 'application/json',
        }
        
        self.handlers = {
                "GET-isPrime": self.handle_is_prime,
                "POST-upload": self.handle_upload,
                "PUT-rename": self.handle_rename,
                "DELETE-remove": self.handle_remove,
                "GET-download": self.handle_download,
                }
        
        
        self.status_codes = {
            200 : 'OK',
            404 : 'Not Found',
            400 : 'Bad Request',
            500 : 'Internal Server Error',
        }
        
        self.uploaddir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files')
        # Get upload directory, create if it does not exist
        if not os.path.exists(self.uploaddir):
            os.mkdir(self.uploaddir)

        
        super().__init__()

    def handle_request(self, data):
        """Handles incoming requests"""
        request = HTTPRequest(data) # Get a parsed HTTP request

        try:
            # Call the corresponding handler method for the current 
            # request's method
            key = f'{request.method}-{request.endpoint}'
            handler = self.handlers[key]
        except KeyError:
            response = {}
            response['status'] = 404
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'Not Found'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
            

        response = handler(request)
        return response


    def response_line(self, status_code):
        """Returns response line (as bytes)"""
        reason = self.status_codes[status_code]
        response_line = 'HTTP/1.1 %s %s\r\n' % (status_code, reason)

        return response_line.encode() # convert from str to bytes

    def response_headers(self, extra_headers=None):
        """Returns headers (as bytes).

        The `extra_headers` can be a dict for sending 
        extra headers with the current response
        """
        headers_copy = self.headers.copy() # make a local copy of headers

        if extra_headers:
            headers_copy.update(extra_headers)

        headers = ''

        for h in headers_copy:
            headers += '%s: %s\r\n' % (h, headers_copy[h])

        return headers.encode() # convert str to bytes


    def handle_is_prime(self, request: HTTPRequest):
        """Handle is prime endpoint"""
        response = {}
        response['status']=200
        
        # Try to get the parameter as int
        
        try:
            num = int(request.qparams['number'])
        # on error, respond accordingly
        except (KeyError, ValueError, TypeError):
            response['status'] = 400
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'Invalid parameter'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        result = True
        # Check if a number is prime
        for i in range(2,int(sqrt(num))+1):
            if num%i==0:
                result = False

        # Craft Response

        response_line = self.response_line(response['status'])
        response_headers = self.response_headers()
        response['number'] = num
        response['isPrime'] = result
        del response['status']
        respbody = json.dumps(response).encode()

        return b''.join([response_line, response_headers, BLANK_LINE, respbody])


    def handle_upload(self, request: HTTPRequest):
        response = {}
        response['status'] = 400
        
        # Handle form data

        if 'Content-Type' in request.headers and 'multipart/form-data' in request.headers["Content-Type"]:
            ctypelist = request.headers['Content-Type'].split('; ')
            boundary = next(bstr.split('=')[1] for bstr in ctypelist if bstr.startswith('boundary'))
            fd = FormData(request.body, boundary.encode())
            self.logger.debug(f'{fd.headers}')

            # I have no idea how tf I wrote this. Extracts filename from the content disposition field

            filename = [subheader.split('=',1)[1].strip('"') for subheader in fd.headers["Content-Disposition"].split('; ') if subheader.startswith('filename')][0]

            # Also guess the extension just in case some guy uploads without the extension
            extension = mimetypes.guess_extension(fd.headers['Content-Type'].split(';',1)[0].strip())
            if not filename.endswith(extension):
                filename = f'{filename}{extension}'
            else:
                del extension

            # Haha path traversal vulnerability go brrrr
            i = 1
            while os.path.exists(os.path.join(self.uploaddir, filename)):
                fn, ext = os.path.splitext(filename)
                filename = f'{fn}({i}){ext}' if i == 1 else f'{fn[:fn.find("(")]}({i}){ext}'
                i += 1
                
            upload_target = os.path.join(self.uploaddir, filename)
                

            with open(upload_target, 'wb+') as outfile:
                self.logger.debug('Upload: writing file')
                outfile.write(fd.formbody)
                response['status'] = 200

        # Craft response
        response_line = self.response_line(response['status'])
        response_headers = self.response_headers()
        if response['status'] == 200:
            response['message'] = 'Successfully uploaded file' if i == 1 else 'Successfully uploaded and renamed file as a file with the same name already exists'
            response['uploadpath'] = os.path.join('files', filename)
        else:
            response['message'] = 'An error occurred'
            
        del response['status']
        respbody = json.dumps(response).encode()

        return b''.join([response_line, response_headers, BLANK_LINE, respbody])


    def handle_rename(self, request: HTTPRequest):
        response = {}
        response['status'] = 500
        try:
            oldfn, newfn = request.qparams['oldFileName'], request.qparams['newName']
        except KeyError:
            response['status'] = 400
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'Invalid parameters'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        if oldfn not in os.listdir(self.uploaddir):
            response['status'] = 200
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'File Not Found'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        oldpath, newpath = os.path.join('files', oldfn), os.path.join('files', newfn)
        os.rename(oldpath, newpath)
        response_line = self.response_line(response['status'])
        response_headers = self.response_headers()
        response['message'] = 'Filename successfully changed'
        response['oldpath'] = oldpath
        response['newpath'] = newpath
        del response['status']
        respbody = json.dumps(response).encode()
        return b''.join([response_line, response_headers, BLANK_LINE, respbody])


    def handle_remove(self, request: HTTPRequest):
        response = {}
        response['status'] = 500
        try:
            fn = request.qparams['fileName']
        except KeyError:
            response['status'] = 400
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'Missing filename parameter'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        if fn not in os.listdir(self.uploaddir):
            response['status'] = 200
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'File Not Found'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        os.remove(os.path.join(self.uploaddir, fn))
        response['message'] = 'File successfully deleted'
        response['filepath'] = os.path.join('files', fn)
        response_line = self.response_line(response['status'])
        response_headers = self.response_headers()
        del response['status']
        respbody = json.dumps(response).encode()
        return b''.join([response_line, response_headers, BLANK_LINE, respbody])


    def handle_download(self, request):
        response = {}
        response['status'] = 500
        try:
            filename = request.qparams['fileName']
        except KeyError:
            response['status'] = 400
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'Missing filename parameter'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        if filename not in os.listdir(self.uploaddir):
            response['status'] = 200
            response_line = self.response_line(response['status'])
            response_headers = self.response_headers()
            response['message'] = 'File Not Found'
            del response['status']
            respbody = json.dumps(response).encode()
            return b''.join([response_line, response_headers, BLANK_LINE, respbody])
        
        filepath = os.path.join(self.uploaddir, filename)
        filesize = os.path.getsize(filepath)
        
        extra_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': mimetypes.guess_type(filepath)[0],
            'Content-Transfer-Encoding': 'binary',
            'Content-Length': filesize,
            }
        with open(filepath, 'rb') as infile:
            respbody = infile.read()
            response['status'] = 200
        response_line = self.response_line(response['status'])
        response_headers = self.response_headers(extra_headers)
        del response
        return b''.join([response_line, response_headers, BLANK_LINE, respbody])
    

if __name__ == '__main__':
    server = HTTPServer()
    server.start()
