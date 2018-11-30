import socket
import sys
import venus6 as v

dev = "/dev/ttyUSB0"
baud = 115200
gps = v.Venus6(dev,baud)

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Connect the socket to the port where the server is listening
server_address = ('192.168.1.111', 5010)
print('connecting to %s port %s' % server_address)
sock.connect(server_address)

print("Probable serial speed: " + str(gps.guessSerialSpeed()))


while True:
    try:

        # Send data
        print("Querying GPS for message...")
        message = gps.readResponse()
        print("sending msg: " + str(message))
        sock.sendall(message[1])
        '''
        # Look for the response
        amount_received = 0
        amount_expected = len(message)

        while amount_received < amount_expected:
            data = sock.recv(16)
            amount_received += len(data)
            if (not (data == "")):
                print("receiving data:")
                print(data)
                id = data[0]
                payload = data[1:-1]
                gps.sendCmd(id,payload)
        '''
    finally:
        print("closing socket")
        #sock.close()
