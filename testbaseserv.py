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
#tracker initialization loop print abbreviation
TRACKINIT = "TRACK_SERV_INIT"
#aggregation server print abbreviation
AGGSERV = "AGG_SERV"
#RTKLIB output client print abbreviation
RTKOUTCLI = "RTKLIB_OUT_CLI"

#cutoff length for output messages
CUTOFF_LEN = 130

#map from tracker IDs to TCP RTKLIB input client objects
tracker_input_map = {}

#list of uninitialized tracker connections
trackserv_init_list = []

#map from TCP tracker client objects to tracker IDs
trackserv_conn_map = {}
aggserv_conn_list = []

def eprint(mess, func_name):
    final_mess = '[' + func_name + ']: ' + mess
    mess_len = len(final_mess)
    if (mess_len > CUTOFF_LEN):
        sys.stdout.write(final_mess[:CUTOFF_LEN] + '...(+' + str(mess_len - CUTOFF_LEN) + ')\n')
    else:
        sys.stdout.write(final_mess + '\n')

def close_init_connection(connection):
    trackserv_init_list.remove(connection)
    connection.close()

def handle_tracker_init():
    while True:
        readable, _, error = select.select(trackserv_init_list, [], [], 1)
        #eprint(len(readable) + ", " + len(error), TRACKINIT)
        for connection in readable:
            try:
                #read in a 5-digit (fixed length) tracker ID
                data = connection.recv(5)
            except socket.error as err:
                eprint(tracker_id + ': socket closed (socket error during read)', TRACKINIT)
                close_init_connection(connection)
                continue
            if data != b'':
                trackserv_init_list.remove(connection)
                tracker_id = data.decode('UTF-8')
                if tracker_id in trackserv_conn_map.values():
                    eprint(tracker_id + ': tracker reconnected', TRACKINIT)
                    trackserv_conn_map[connection] = tracker_id
                    for conn in trackserv_conn_map.keys():
                        if trackserv_conn_map[conn] == tracker_id:
                            eprint(tracker_id + ': old connection deleted', TRACKINIT)
                            del trackserv_conn_map[conn]
                            break
                    connection.sendall(b'OK')
                    continue
                eprint(tracker_id + ': new tracker connection established', TRACKINIT)
                #obtain free input and output ports for use by RTKLIB
                input_port = get_free_tcp_port()
                output_port = get_free_tcp_port()
                #spawn RTKLIB process with these params
                spawn_rtklib(input_port, output_port, tracker_id)
                #wait for RTKLIB to get its network all set up
                time.sleep(3)
                #create the output client for interfacing with RTKLIB
                _thread.start_new_thread(output_sock, (tracker_id, output_port))
                #create the input client for interfacing with RTKLIB
                input_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                input_sock_address = ('127.0.0.1', input_port)
                input_sock.connect(input_sock_address)
                #keep track of input client and associated tracker_id
                tracker_input_map[tracker_id] = input_sock
                trackserv_conn_map[connection] = tracker_id
                #tell tracker we're ready to receive GPS data
                connection.sendall(b'OK')
            else:
                eprint('tracker_id not yet sent for new connection', TRACKINIT)
                time.sleep(5)
        for connection in error:
            eprint(tracker_id + ': socket error (socket error by select)', TRACKINIT)
            close_init_connection(connection)

def close_tracker_connection(connection):
    tracker_id = trackserv_conn_map[connection]
    del trackserv_conn_map[connection]
    connection.close()
    tracker_input_map[tracker_id].close()
    del tracker_input_map[tracker_id]
    
def handle_tracker_connections():
    #TODO creating a thread for each connection might perform better than a for loop here for large numbers of trackers
    while True:
        readable, writable, error = select.select(list(trackserv_conn_map.keys()), [], [], 1)
        for connection in readable:
            tracker_id = trackserv_conn_map[connection]
            try:
                data = connection.recv(4096)
            except socket.error as err:
                eprint(tracker_id + ': socket closed (socket error during read)', TRACKSERV)
                close_tracker_connection(connection)
                continue
            if data != b'':
                gps_message = data
                eprint(tracker_id + ': GPS message: ' + str(gps_message), TRACKSERV)
                #send its data along to its associated RTKLIB
                tracker_input_map[tracker_id].sendall(gps_message)
            else:
                eprint(tracker_id + ': socket closed (read empty string)', TRACKSERV)
                close_tracker_connection(connection)
        for connection in error:
            eprint(tracker_id + ': socket error (socket error by select)', TRACKSERV)
            close_tracker_connection(connection)

def run_tracker_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 1)
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 15)
    sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 1)
    eprint('(' + TRACKSERV_ADDR[0] + ":" + str(TRACKSERV_ADDR[1]) + '): starting up tracker server', TRACKSERV)
    sock.bind(TRACKSERV_ADDR)
    #allow a maximum of 200 connected boats
    sock.listen(200)
    #listen for connections from trackers
    while True:
        connection, client_address = sock.accept()
        if (connection not in list(trackserv_conn_map.keys())) and (connection not in trackserv_init_list):
            trackserv_init_list.append(connection)

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
    _thread.start_new_thread(handle_tracker_init, ())
    _thread.start_new_thread(handle_tracker_connections, ())
    run_tracker_server()
