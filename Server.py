# Import socket module
from socket import * 
import sys # In order to terminate the program
from urllib.parse import urlparse, parse_qs

# Create a TCP server socket
#(AF_INET is used for IPv4 protocols)
#(SOCK_STREAM is used for TCP)

serverSocket = socket(AF_INET, SOCK_STREAM)

# Assign a port number
serverPort = 6788

# Bind the socket to server address and server port
serverSocket.bind(("", serverPort))

# Listen to at most 1 connection at a time
serverSocket.listen(1)

# Server should be up and running and listening to the incoming connections

while True:
        print('The server is ready to receive')

        # Set up a new connection from the client
        connectionSocket, addr = serverSocket.accept()

        # Respond to request so long as no exceptions occur
        try:
                # Receives the request message from the client
                message = connectionSocket.recv(1024).decode()
                # Extract the path of the requested object from the message
                # The path is the second part of HTTP header, identified by [1]
                
                url = urlparse(message.split()[1])

                if url.path == "/":
                		#get html file
                        filename = "/index.html"
                        f = open(filename[1:],mode="rb")
                        outputdata = f.read()
                        #send OK
                        connectionSocket.send("HTTP/1.1 200 OK\r\n\r\n".encode()) 
                        
                elif url.path == "/submit":
                		#parse query
                        q = parse_qs(url.query)
                        #form html
                        outputdata = "<p>Your name is "+q["name"][0]
                        outputdata += "</p><p>Your favorite color is <font color='"
                        outputdata += q["color"][0]+"'>"+q["color"][0]+"</font></p>"
                        outputdata = outputdata.encode()
                        #send OK
                        connectionSocket.send("HTTP/1.1 200 OK\r\n\r\n".encode()) 
                        
                else:	
                		#get html file
                        filename = "/404.html"
                        f = open(filename[1:],mode="rb")
                        outputdata = f.read()
                        #send error
                        connectionSocket.send("HTTP/1.1 404 Not Found\r\n\r\n".encode()) 
                        
                # Send the content of the requested file to the connection socket
                connectionSocket.send(outputdata)
                connectionSocket.send("\r\n".encode())
                                
                # Close the client connection socket
                connectionSocket.close()

        except IOError:
                        # Send HTTP response message for server error
                        connectionSocket.send("HTTP/1.1 500 Internal Server Error\r\n\r\n".encode())
                        connectionSocket.send("<html><head></head><body><h1>500 Internal Server Error</h1></body></html>\r\n".encode())
                        # Close the client connection socket
                        connectionSocket.close()

serverSocket.close()  
sys.exit()#Terminate the program after sending the corresponding data
