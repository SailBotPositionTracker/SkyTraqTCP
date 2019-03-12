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
TRACKSERV_PORT = 8000
TRACKSERV_ADDR = (IP, TRACKSERV_PORT)

#port for aggreggation server
AGGSERV_PORT = 9000
AGGSERV_ADDR = (IP, AGGSERV_PORT)

#tracker server print abbreviation
TRACKSERV = "TRACK_SERV"
#aggregation server print abbreviation
AGGSERV = "AGG_SERV"
#RTKLIB output client print abbreviation
RTKOUTCLI = "RTKLIB_OUT_CLI"

#cutoff length for output messages
CUTOFF_LEN = 130

#map from tracker IDs to TCP client objects
tracker_input_map = {}

trackserv_conn_list = []
aggserv_conn_list = []

def eprint(mess, func_name):
    final_mess = '[' + func_name + ']: ' + mess
    mess_len = len(final_mess)
    if (mess_len > CUTOFF_LEN):
        sys.stdout.write(final_mess[:CUTOFF_LEN] + '...(+' + str(mess_len - CUTOFF_LEN) + ')\n')
    else:
        sys.stdout.write(final_mess + '\n')

def handle_tracker_connections():
    #TODO creating a thread for each connection might perform better than a for loop here for large numbers of trackers
    while True:
        readable, _, _ = select.select(trackserv_conn_list, [], [], 1)
        for connection in readable:
            try:
                data = connection.recv(4096)
            except socket.error as err:
                eprint(tracker_id + ': socket error: ' + str(err), TRACKSERV)
                continue
            if data != b'':
                #TODO for testing
                tracker_id = "T1234"
                #print(len(data))
                #parts = data.split('\t', 1)
                #tracker_id = parts[0]
                #TODO for testing
                gps_message = data
                #gps_message = parts[1]
                eprint(tracker_id + ': GPS message: ' + str(gps_message), TRACKSERV)
                #send its data along to its associated RTKLIB
                tracker_input_map[tracker_id].sendall(gps_message)
            else:
                #tracker connection closed remotely, clean everything up
                eprint(tracker_id + ': socket closed', TRACKSERV)
                connection.close()
                trackserv_conn_list.remove(connection)
                tracker_input_map[tracker_id].close()
                del tracker_input_map[tracker_id]

def run_tracker_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            spawn_rtklib(input_port, output_port, tracker_id)
            time.sleep(3)
            _thread.start_new_thread(output_sock, (tracker_id, output_port))
            input_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            input_sock_address = ('127.0.0.1', input_port)
            input_sock.connect(input_sock_address)
            tracker_input_map[tracker_id] = input_sock
            trackserv_conn_list.append(connection)

def spawn_rtklib(input_port, output_port, tracker_id):
    eprint('RTKLIB input port: ' + str(input_port) + ', output port: ' + str(output_port), TRACKSERV)
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
    subprocess.Popen(args)

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
    output_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    output_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    output_sock_address = ('127.0.0.1', output_port)
    eprint(tracker_id + '(' + output_sock_address[0] + ":" + str(output_sock_address[1]) + '): started up RTKLIB output client', RTKOUTCLI)
    output_sock.connect(output_sock_address)
    eprint(tracker_id + ': output connection established with RTKLIB', RTKOUTCLI)
    while True:
        try:
            data = output_sock.recv(1024)
        except socket.error as err:
            eprint(tracker_id + ': socket error: ' + str(err), RTKOUTCLI)
            break
        if data != b'':
            eprint(tracker_id + ': RTKLIB message: "' + str(data) + '"', RTKOUTCLI)
            #ignore message if first character is % (RTKLIB headers)
            if data[0] != 37:
                parsed_data = parse_data_from_rtklib(tracker_id, data)
                for ext_conn in aggserv_conn_list:
                    ext_conn.sendall(parsed_data)
        else:
            eprint(tracker_id + ': socket closed', RTKOUTCLI)
            break
    #TODO is this correct?
    output_sock.close()

def parse_data_from_rtklib(tracker_id, data):
    #input format example: '2038, 417928.999, 1.000, 2.000, 3.000, 5, 7, 6.6558, 3.1100, 2.8179, -3.3301, 1.9243, -3.2028, 0.00, 0.0'
    #output format example: '12345,0001,0000001.000,-000000001.0000,-000000001.0000'
    data_parts = data.decode('UTF-8').split(',')
    #WWWW (unsigned)
    gpst_week = "{:4.0f}".format(float(data_parts[0]))
    #SSSSSSS.SSS (unsigned)
    gpst_seconds = "{:11.3f}".format(float(data_parts[1]))
    #+eeeeeeeee.eeee (signed)
    east = "{:15.4f}".format(float(data_parts[2]))
    #+nnnnnnnnn.nnnn (signed)
    north = "{:15.4f}".format(float(data_parts[3]))
    out_str = "{},{},{},{},{}".format(tracker_id, gpst_week, gpst_seconds, east, north)
    return out_str.encode('UTF-8')

if __name__ == "__main__":
    with open(CONFIG_FILE, 'r') as myfile:
        CONFIG = myfile.read()
    _thread.start_new_thread(run_aggregator_server, ())
    _thread.start_new_thread(handle_tracker_connections, ())
    run_tracker_server()
