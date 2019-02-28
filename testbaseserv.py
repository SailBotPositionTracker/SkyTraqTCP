#!/bin/python3
import socket
import select
import sys
import subprocess
import time
import _thread

# Getting a random free tcp port in python using sockets
def get_free_tcp_port():
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(('', 0))
    port = tcp.getsockname()[1]
    tcp.close()
    return port

#path to config file (without I/O params)
CONFIG_FILE = '../rtk_test.conf'

#static IP address for base station
IP = '192.168.4.1'
#port for tracker server
TRACKSERV_PORT = 8001
TRACKSERV_ADDR = (IP, TRACKSERV_PORT)

#port for aggreggation server
AGGSERV_PORT = 9001
AGGSERV_ADDR = (IP, AGGSERV_PORT)

#tracker server print abbreviation
TRACKSERV = "TRACK_SERV"
#aggregation server print abbreviation
AGGSERV = "AGG_SERV"
#RTKLIB output server print abbreviation
RTKOUTSERV = "RTKLIB_OUT_SERV"

#map from tracker IDs to TCP client objects
tracker_input_map = {}

trackserv_conn_list = []
aggserv_conn_list = []

def eprint(mess, func_name):
    sys.stdout.write('[' + func_name + ']: ' + mess + '\n')

def handle_tracker_connections():
    #TODO try/catch/finally for disconnections
    while True:
        for connection in trackserv_conn_list:
            data = connection.recv(4096)
            if data != "":
                #TODO for testing
                tracker_id = "T1234"
                #print(len(data))
                #parts = data.split('\t', 1)
                #tracker_id = parts[0]
                #TODO for testing
                gps_message = data
                #gps_message = parts[1]
                #TODO commented out for cmdline readability
                #eprint(tracker_id + ': received gps message', TRACKSERV)
                #send its data along to its associated RTKLIB
                tracker_input_map[tracker_id].sendall(gps_message)
            else:
                #tracker connection closed, clean everything up
                eprint(tracker_id + ': socket closed', TRACKSERV)
                connection.close()
                trackserv_conn_list.remove(connection)
                tracker_input_map[tracker_id].close()
                del tracker_input_map[tracker_id]

def run_tracker_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #60 second timeout
    sock.settimeout(60)
    eprint('(' + TRACKSERV_ADDR[0] + ":" + str(TRACKSERV_ADDR[1]) + '): starting up tracker server', TRACKSERV)
    sock.bind(TRACKSERV_ADDR)
    #allow a maximum of 200 connected boats
    sock.listen(200)
    #listen for connections from trackers
    while True:
        connection, client_address = sock.accept()
        if connection not in trackserv_conn_list:
            #TODO for testing
            tracker_id = "T1234"
            data = connection.recv(4096)
            #print(len(data))
            #parts = data.split('\t', 1)
            #tracker_id = parts[0]
            eprint(tracker_id + '(' + client_address[0] + ":" + str(client_address[1]) + '): new tracker connection established', TRACKSERV)
            input_port = get_free_tcp_port()
            output_port = get_free_tcp_port()
            #spawn RTKLIB process with these params
            _thread.start_new_thread(output_sock, (tracker_id, output_port))
            spawn_rtklib(input_port, output_port, tracker_id)
            time.sleep(3)
            input_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            #60 second timeout for input from tracker
            input_sock.settimeout(60)
            input_sock_address = ('127.0.0.1', input_port)
            input_sock.connect(input_sock_address)
            tracker_input_map[tracker_id] = input_sock
            trackserv_conn_list.append(connection)

def spawn_rtklib(input_port, output_port, tracker_id):
    new_config = CONFIG
    #set input
    new_config += "\ninpstr1-path       =127.0.0.1:" + str(input_port)
    #set output
    new_config += "\noutstr1-path       =127.0.0.1:" + str(output_port)
    #create config file
    new_file_name = "rtk_" + tracker_id + ".conf"
    new_file = open(new_file_name, "w")
    new_file.write(new_config)
    new_file.close()
    #start the RTKLIB process
    args = ['./rtkrcv', '-s', '-o', new_file_name]
    subprocess.Popen(args, stdout=subprocess.DEVNULL)

def run_aggregator_server():
    aggregator = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    aggregator.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    eprint('(' + AGGSERV_ADDR[0] + ":" + str(AGGSERV_ADDR[1]) + '): starting up aggregator server', AGGSERV)
    aggregator.bind(AGGSERV_ADDR)
    #allow 20 external devices to connect to this server
    aggregator.listen(20)
    #listen for connections from trackers
    while True:
        connection, client_address = aggregator.accept()
        if connection not in aggserv_conn_list:
            eprint('(' + client_address[0] + ":" + str(client_address[1]) + '): aggregator connection established with external device', AGGSERV)
            aggserv_conn_list.append(connection)

def output_sock(tracker_id, output_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #60 second timeout for output from RTKLIB
    server_address = ('127.0.0.1', output_port)
    sock.bind(server_address)
    #allow only one connection to this output server
    sock.listen(1)
    eprint(tracker_id + '(' + server_address[0] + ":" + str(server_address[1]) + '): started up RTKLIB output server', RTKOUTSERV)
    connection = sock.accept()[0]
    eprint(tracker_id + ': output connection established with RTKLIB', RTKOUTSERV)
    while True:
        print("CHECKING")
        ready = select.select([connection], [], [], 60)
        print("DONE CHECKING")
        if ready[0]:
            try:
                print("READING")
                data = connection.recv(1024)
                print("DONE READING")
            except socket.error as err:
                eprint(tracker_id + ': socket error: ' + str(err), RTKOUTSERV)
                break
            except:
                print("Unexpected error: ", sys.exc_info()[0])
                raise
            if data != b'':
                eprint(tracker_id + ': RTKLIB message: "' + str(data) + '"', RTKOUTSERV)
                #ignore message if first character is % (RTKLIB headers)
                if data[0] != 37:
                    print("SENDING DATA")
                    parsed_data = parse_data_from_rtklib(tracker_id, data)
                    for ext_conn in aggserv_conn_list:
                        print("SENDING DATA LOOP")
                        ext_conn.sendall(parsed_data)
            else:
                eprint(tracker_id + ': socket closed', RTKOUTSERV)
                break
    connection.close()

def parse_data_from_rtklib(tracker_id, data):
    #input format example: '2038, 417928.999, 1.000, 2.000, 3.000, 5, 7, 6.6558, 3.1100, 2.8179, -3.3301, 1.9243, -3.2028, 0.00, 0.0'
    #output format example: 'T1234,0001,0000001.000,000000001.0000,000000002.0000'
    data_parts = data.decode('UTF-8').split(',')
    gpst_week = "{:4.0f}".format(float(data_parts[0]))
    gpst_seconds = "{:10.3f}".format(float(data_parts[1]))
    east = "{:14.4f}".format(float(data_parts[2]))
    north = "{:14.4f}".format(float(data_parts[3]))
    out_str = "{},{},{},{},{}".format(tracker_id, gpst_week, gpst_seconds, east, north)
    return out_str.encode('UTF-8')


if __name__ == "__main__":
    with open(CONFIG_FILE, 'r') as myfile:
        CONFIG = myfile.read()
    _thread.start_new_thread(run_aggregator_server, ())
    _thread.start_new_thread(handle_tracker_connections, ())
    run_tracker_server()
