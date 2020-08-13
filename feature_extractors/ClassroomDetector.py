import csv
import datetime
import time
from operator import itemgetter
from collections import defaultdict
import winsound

'''
various config settings:
file_input is input raw .csv files
delim_type is the delimiter for the raw; usually this is \t
dt_format is the datetime format from the "server_time" column
class_size is the bounds on the number of unique session IDs that are considered to be a class
class_window is the max duration between any two unique session starts to be considered a class
duration is the bounds on the duration of a given game session
hexads are the number of hexads in the ip that you want to look at
afk duration is the maximum amount of time between two user-generated actions to not be considered afk
'''

#file_input = "D:\\Field Day Lab\\Raw_LAKELAND_2019Dec_iter1.csv"
file_input = "D:\\Field Day Lab\\LAKELAND_20200301_to_20200331\\LAKELAND_20200301_to_20200331_a9720c1_raw.csv"
#file_input = "D:\\Field Day Lab\\LAKELAND_20200401_to_20200430\\LAKELAND_20200401_to_20200430_a9720c1_raw.csv"
file_output = file_input[:-4] + "_classroom_subset.csv"
delim_type = "\t"
dt_format = "%Y-%m-%d %H:%M:%S"
class_size_lower = 10
class_size_upper = 45
class_window = 600
duration_lower = 180
duration_upper = 4200
hexads = 4
afk_duration = 60

def process_main(f_in, dt_fmt):
    '''
    Shell function for handling various classroom identification operations.
    '''

    with open(f_in) as f:
        data = list(csv.reader(f,delimiter=delim_type))
    header = {v:k for k,v in enumerate(data[0])}
    header_list = data[0]

    def preprocess(_data):
        '''
        Shortens remote_addr to the first three digits of session IP.
        Converts server_time to UNIX
        '''
        for i in _data[1:]:
            if hexads != 4:
                ip_shortened = i[header['remote_addr']].split(".")[:(4 - hexads) * -1]
                i[header['remote_addr']] = ".".join(ip_shortened)
            i[header['server_time']] = int(
                time.mktime(datetime.datetime.strptime(i[header['server_time']], dt_fmt).timetuple()))

        # sorting the file in preparation for iterating through it
        _data = sorted(_data[1:], key=itemgetter(header['remote_addr'], header['session_id'], header['server_time']))
        _data = [x for x in _data[1:] if int(x[header['event_custom']]) <= 16] # selecting only student actions
        _data = [header_list] + _data # adding the header row back in
        return _data

    f_data = preprocess(data)
    return f_data

if __name__ == '__main__':
    data = process_main(file_input,dt_format)
    header_list = data[0]
    header = {v: k for k, v in enumerate(data[0])}
    ip_session_dict = defaultdict(list)
    last_timestamp = data[1][header['server_time']]
    ids_to_exclude = []

    for n, i in enumerate(data):
        # if a session id changes, we need to record the new start time and old end time
        if i[header['session_id']] != data[n-1][header['session_id']]:
            old_key = data[n-1][header['remote_addr']] + "_" + data[n-1][header['session_id']]
            ip_session_dict[old_key].append(data[n-1][header['server_time']])

            new_key = i[header['remote_addr']] + "_" + i[header['session_id']]
            ip_session_dict[new_key].append(i[header['server_time']])

        # while we're within a session, if there's a long gap of inactivity, we need to exclude that session
        elif i[header['server_time']] - last_timestamp > afk_duration:
            ids_to_exclude.append(i[header['remote_addr']] + "_" + i[header['session_id']])

        last_timestamp = i[header['server_time']]

    # removing the afk sessions from our analysis
    ip_session_dict.pop('remote_addr_session_id')
    for i in ids_to_exclude:
        try:
            ip_session_dict.pop(i)
        except:
            pass

    overlaps_bystart = defaultdict(list)
    overlaps_byend = defaultdict(list)

    for key in ip_session_dict:
        session_start = int(ip_session_dict[key][0])
        session_end = int(ip_session_dict[key][-1])

        for key2 in ip_session_dict:
            overlap = False
            if key2 != key:
                if session_start <= int(ip_session_dict[key2][0]) <= session_end:
                    overlaps_bystart[key].append([key2,
                                                  session_start,
                                                  session_end,
                                                  ip_session_dict[key2][0],
                                                  ip_session_dict[key2][-1]])
                    overlap = True
                if session_start <= int(ip_session_dict[key2][-1]) <= session_end:
                    overlaps_byend[key].append(key2)
                    overlap = True

    writer = csv.writer(open("Lakeland IP Blocks By Timestamp.csv","w",newline=""))
    for key in overlaps_bystart:
        if len(overlaps_bystart[key]) > 10:
            writer.writerow(key)
            for val in overlaps_bystart[key]:
                writer.writerow(val)
            writer.writerow([])