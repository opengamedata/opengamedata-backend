# global imports
from mysql.connector import connect, connection, cursor
import http
import logging
import math
import sshtunnel
import traceback
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union
# local imports
from interfaces.DataInterface import DataInterface
from schemas.GameSchema import GameSchema
from schemas.TableSchema import TableSchema
from utils import Logger


## Dumb struct to collect data used to establish a connection to a SQL database.
class SQLLogin:
    def __init__(self, host: str, port: int, user: str, pword: str, db_name: str):
        self.host    = host
        self.port    = port
        self.user    = user
        self.pword   = pword
        self.db_name = db_name

## Dumb struct to collect data used to establish a connection over ssh.
class SSHLogin:
    def __init__(self, host: str, port: int, user: str, pword: str):
        self.host    = host
        self.port    = port
        self.user    = user
        self.pword   = pword

## @class SQL
#  A utility class containing some functions to assist in retrieving from a database.
#  Specifically, helps to connect to a database, make selections, and provides
#  a nicely formatted 500 error message.
class SQL:
    # Function to set up a connection to a database, via an ssh tunnel if available.
    @staticmethod
    def prepareDB(db_settings:Dict[str,Any], ssh_settings:Union[Dict[str,Any],None]=None) -> Tuple[Union[sshtunnel.SSHTunnelForwarder,None], Union[connection.MySQLConnection,None]]:
        """
        Function to set up a connection to a database, via an ssh tunnel if available.

        :param db_settings: A dictionary mapping names of database parameters to values.
        :type db_settings: Dict[str,Any]
        :param ssh_settings: A dictionary mapping names of ssh parameters to values, or None if no ssh connection is desired., defaults to None
        :type ssh_settings: Union[Dict[str,Any],None], optional
        :return: A tuple consisting of the tunnel and database connection, respectively.
        :rtype: Tuple[Union[sshtunnel.SSHTunnelForwarder,None], Union[connection.MySQLConnection,None]]
        """
        tunnel  : Union[sshtunnel.SSHTunnelForwarder,None] = None
        db_conn : Union[connection.MySQLConnection,None]   = None
        # Load settings, set up consts.
        DB_NAME_DATA = db_settings["DB_NAME_DATA"]
        DB_USER = db_settings['DB_USER']
        DB_PW = db_settings['DB_PW']
        DB_HOST = db_settings['DB_HOST']
        DB_PORT = db_settings['DB_PORT']
        sql_login = SQLLogin(host=DB_HOST, port=DB_PORT, user=DB_USER, pword=DB_PW, db_name=DB_NAME_DATA)
        Logger.toStdOut("Preparing database connection...", logging.INFO)
        if ssh_settings is not None:
            SSH_USER = ssh_settings['SSH_USER']
            SSH_PW = ssh_settings['SSH_PW']
            SSH_HOST = ssh_settings['SSH_HOST']
            SSH_PORT = ssh_settings['SSH_PORT']
            if (SSH_HOST != "" and SSH_USER != "" and SSH_PW != ""):
                ssh_login = SSHLogin(host=SSH_HOST, port=SSH_PORT, user=SSH_USER, pword=SSH_PW)
                tunnel,db_conn = SQL.connectToMySQLViaSSH(sql=sql_login, ssh=ssh_login)
        else:
            db_conn = SQL.connectToMySQL(login=sql_login)
            tunnel = None
        Logger.toStdOut("Done preparing database connection.", logging.INFO)
        return (tunnel, db_conn)

    # Function to help connect to a mySQL server.
    @staticmethod
    def connectToMySQL(login: SQLLogin) -> Union[connection.MySQLConnection, None]:
        """Function to help connect to a mySQL server.

        Simply tries to make a connection, and prints an error in case of failure.
        :param login: A SQLLogin object with the data needed to log into MySQL.
        :type login: SQLLogin
        :return: If successful, a MySQLConnection object, otherwise None.
        :rtype: Union[connection.MySQLConnection, None]
        """
        try:
            db_conn = connection.MySQLConnection(host     = login.host,    port    = login.port,
                                                 user     = login.user,    password= login.pword,
                                                 database = login.db_name, charset = 'utf8')
            Logger.toStdOut(f"Connected to SQL (no SSH) at {login.host}:{login.port}/{login.db_name}, {login.user}", logging.INFO)
            return db_conn
        #except MySQLdb.connections.Error as err:
        except Exception as err:
            msg = f"Could not connect to the MySql database: {type(err)} {str(err)}"
            Logger.toStdOut(msg, logging.ERROR)
            Logger.toPrint(msg, logging.ERROR)
            traceback.print_tb(err.__traceback__)
            return None

    ## Function to help connect to a mySQL server over SSH.
    @staticmethod
    def connectToMySQLViaSSH(sql: SQLLogin, ssh: SSHLogin) -> Tuple[Union[sshtunnel.SSHTunnelForwarder,None], Union[connection.MySQLConnection,None]]:
        """Function to help connect to a mySQL server over SSH.

        Simply tries to make a connection, and prints an error in case of failure.
        :param sql: A SQLLogin object with the data needed to log into MySQL.
        :type sql: SQLLogin
        :param ssh: An SSHLogin object with the data needed to log into MySQL.
        :type ssh: SSHLogin
        :return: An open connection to the database if successful, otherwise None.
        :rtype: Tuple[Union[sshtunnel.SSHTunnelForwarder,None], Union[connection.MySQLConnection,None]]
        """
        tunnel : Union[sshtunnel.SSHTunnelForwarder, None] = None
        db_conn   : Union[connection.MySQLConnection, None] = None
        MAX_TRIES : int = 5
        tries : int = 0
        connected_ssh : bool = False

        # First, connect to SSH
        while connected_ssh == False and tries < MAX_TRIES:
            if tries > 0:
                Logger.toStdOut("Re-attempting to connect to SSH.", logging.INFO)
            try:
                tunnel = sshtunnel.SSHTunnelForwarder(
                    (ssh.host, ssh.port), ssh_username=ssh.user, ssh_password=ssh.pword,
                    remote_bind_address=(sql.host, sql.port), logger=Logger.std_logger
                )
                tunnel.start()
                connected_ssh = True
                Logger.toStdOut(f"Connected to SSH at {ssh.host}:{ssh.port}, {ssh.user}", logging.INFO)
            except Exception as err:
                msg = f"Could not connect to the SSH: {type(err)} {str(err)}"
                Logger.Log(msg, logging.ERROR)
                Logger.toPrint(msg, logging.ERROR)
                traceback.print_tb(err.__traceback__)
                tries = tries + 1
        if connected_ssh == True and tunnel is not None:
            # Then, connect to MySQL
            try:
                db_conn = connection.MySQLConnection(host     = sql.host,    port    = tunnel.local_bind_port,
                                                     user     = sql.user,    password= sql.pword,
                                                     database = sql.db_name, charset ='utf8')
                Logger.toStdOut(f"Connected to SQL (via SSH) at {sql.host}:{tunnel.local_bind_port}/{sql.db_name}, {sql.user}", logging.INFO)
                return (tunnel, db_conn)
            except Exception as err:
                msg = f"Could not connect to the MySql database: {type(err)} {str(err)}"
                Logger.Log(msg, logging.ERROR)
                Logger.toPrint(msg, logging.ERROR)
                traceback.print_tb(err.__traceback__)
                if tunnel is not None:
                    tunnel.stop()
                return (None, None)
        else:
            return (None, None)

    @staticmethod
    def disconnectMySQLViaSSH(tunnel:Union[sshtunnel.SSHTunnelForwarder,None], db:Union[connection.MySQLConnection,None]) -> None:
        if db is not None:
            db.close()
            Logger.toStdOut("Closed database connection", logging.INFO)
        # else:
        #     Logger.toStdOut("No db to close.", logging.INFO)
        if tunnel is not None:
            tunnel.stop()
            Logger.toStdOut("Stopped tunnel connection", logging.INFO)
        # else:
        #     Logger.toStdOut("No tunnel to stop", logging.INFO)

    # Function to build and execute SELECT statements on a database connection.
    @staticmethod
    def SELECT(cursor      :cursor.MySQLCursor,    db_name       :str,         table         :str,
               columns     :List[str] = None,  join          :str = None,  filter        :str = None,
               sort_columns:List[str] = None,  sort_direction:str = "ASC", grouping      :str = None,
               distinct    :bool      = False, limit         :int = -1,    fetch_results :bool = True) -> Union[List[Tuple],None]:
        """Function to build and execute SELECT statements on a database connection.

        :param cursor: A database cursor, retrieved from the active connection.
        :type cursor: cursor.MySQLCursor
        :param db_name: The name of the database to which we are connected.
        :type db_name: str
        :param table: The name of the table from which we want to make a selection.
        :type table: str
        :param columns: A list of columns to be selected. If empty (or None), all columns will be used (SELECT * FROM ...). Defaults to None
        :type columns: List[str], optional
        :param join: [description], defaults to None
        :type join: str, optional
        :param filter: A string giving the constraints for a WHERE clause (The "WHERE" term itself should not be part of the filter string), defaults to None
        :type filter: str, optional
        :param sort_columns: A list of columns to sort results on. The order of columns in the list is the order given to SQL. Defaults to None
        :type sort_columns: List[str], optional
        :param sort_direction: The "direction" of sorting, either ascending or descending., defaults to "ASC"
        :type sort_direction: str, optional
        :param grouping: A column name to group results on. Subject to SQL rules for grouping, defaults to None
        :type grouping: str, optional
        :param distinct: A bool to determine whether to select only rows with distinct values in the column, defaults to False
        :type distinct: bool, optional
        :param limit: The maximum number of rows to be selected. Use -1 for no limit., defaults to -1
        :type limit: int, optional
        :param fetch_results: A bool to determine whether all results should be fetched and returned, defaults to True
        :type fetch_results: bool, optional
        :return: A collection of all rows from the selection, if fetch_results is true, otherwise None.
        :rtype: Union[List[Tuple],None]
        """
        query = SQL._prepareSelect(db_name=db_name, table=table, columns=columns, join=join, filter=filter,
                                   sort_columns=sort_columns, sort_direction=sort_direction, grouping=grouping,
                                   distinct=distinct, limit=limit)
        return SQL.SELECTfromQuery(cursor=cursor, query=query, fetch_results=fetch_results)

    @staticmethod
    def SELECTfromQuery(cursor:cursor.MySQLCursor, query: str, fetch_results: bool = True) -> Union[List[Tuple], None]:
        result : Union[List[Tuple], None] = None
        # first, we do the query.
        Logger.toStdOut(f"Running query: {query}", logging.DEBUG)
        start = datetime.now()
        cursor.execute(query)
        time_delta = datetime.now()-start
        Logger.toStdOut(f"Query execution completed, time to execute: {time_delta}", logging.DEBUG)
        # second, we get the results.
        if fetch_results:
            result = cursor.fetchall()
            time_delta = datetime.now()-start
            Logger.toStdOut(f"Query fetch completed, total query time:    {time_delta} to get {len(result) if result is not None else 0:d} rows", logging.DEBUG)
        return result

    @staticmethod
    def _prepareSelect(db_name: str,                    table:str,
                       columns: List[str]      = None,  join: str      = None,  filter: str = None,
                       sort_columns: List[str] = None,  sort_direction = "ASC", grouping: str = None,
                       distinct: bool          = False, limit: int     = -1) -> str:
        d = "DISTINCT " if distinct else ""
        cols      = ",".join(columns)      if columns is not None      and len(columns) > 0      else "*"
        sort_cols = ",".join(sort_columns) if sort_columns is not None and len(sort_columns) > 0 else None
        table_path = db_name + "." + str(table)

        sel_clause   = "SELECT " + d + cols + " FROM " + table_path
        join_clause  = "" if join      is None else f" {join}"
        where_clause = "" if filter    is None else f" WHERE {filter}"
        group_clause = "" if grouping  is None else f" GROUP BY {grouping}"
        sort_clause  = "" if sort_cols is None else f" ORDER BY {sort_cols} {sort_direction} "
        lim_clause   = "" if limit < 0         else f" LIMIT {str(limit)}"

        return sel_clause + join_clause + where_clause + group_clause + sort_clause + lim_clause + ";"

    ## Function similar to SELECTfromQuery, but gets the first element per-col in cursor.fetchall().
    #  Really, it's probably meant to be row, rather than col.
    #  @param cursor        The MySQLdb cursor for accessing the database.
    #  @param query         A string representing the query to execute.
    #  @param fetch_results A bool to determine whether we should try to return the query results or not.
    @staticmethod
    def Query(cursor:cursor.MySQLCursor, query: str, fetch_results: bool = True) -> Union[List[Tuple], None]:
        result : Union[List[Tuple], None] = None
        # first, we do the query.
        Logger.toStdOut("Running query: " + query, logging.DEBUG)
        start = datetime.now()
        cursor.execute(query)
        time_delta = datetime.now()-start
        Logger.toStdOut(f"Query execution completed, time to execute: {time_delta}", logging.DEBUG)
        # second, we get the results.
        if fetch_results:
            result = [col[0] for col in cursor.fetchall()]
            time_delta = datetime.now()-start
            Logger.toStdOut(f"Query fetch completed, total query time:    {time_delta} to get {len(result):d} rows", logging.DEBUG)
        return result

    ## Simple function to construct and log a nice server 500 error message.
    #  @param err_msg A more detailed error message with info to help debugging.
    @staticmethod
    def server500Error(err_msg: str):
        val = http.HTTPStatus.INTERNAL_SERVER_ERROR.value
        phrase = http.HTTPStatus.INTERNAL_SERVER_ERROR.phrase
        Logger.toStdOut(f"HTTP Response: {val}{phrase}", logging.ERROR)
        Logger.toStdOut(f"Error Message: {err_msg}", logging.ERROR)

class MySQLInterface(DataInterface):
    def __init__(self, game_id:str, settings):
        # set up data from params
        super().__init__(game_id=game_id)
        self._settings = settings
        # set up connection vars and try to make connection off the bat.
        self._tunnel : Union[sshtunnel.SSHTunnelForwarder, None] = None
        self._db : Union[connection.MySQLConnection, None] = None
        self._db_cursor : Union[cursor.MySQLCursor, None] = None
        self.Open()
        
    def _open(self, force_reopen:bool = False) -> bool:
        if force_reopen:
            self.Close()
            self.Open(force_reopen=False)
        if not self._is_open:
            start = datetime.now()
            self._tunnel, self._db = SQL.prepareDB(db_settings=self._settings["db_config"], ssh_settings=self._settings["ssh_config"])
            if self._tunnel != None and self._db != None:
                self._db_cursor = self._db.cursor()
                self._is_open = True
                time_delta = datetime.now() - start
                Logger.Log(f"Database Connection Time: {time_delta}", logging.INFO)
                return True
            else:
                SQL.disconnectMySQLViaSSH(tunnel=self._tunnel, db=self._db)
                return False
        else:
            return True

    def _close(self) -> bool:
        SQL.disconnectMySQLViaSSH(tunnel=self._tunnel, db=self._db)
        Logger.toStdOut("Closed connection to MySQL.", logging.DEBUG)
        self._is_open = False
        return True

    def _rowsFromIDs(self, id_list: List[int], versions: Union[List[int],None]=None) -> List[Tuple]:
        # grab data for the given session range. Sort by event time, so
        if not self._db_cursor == None:
            if versions is not None and versions is not []:
                ver_filter = f" AND app_version in ({','.join([str(version) for version in versions])}) "
            else:
                ver_filter = ''
            id_string = ','.join([f"'{x}'" for x in id_list])
            # filt = f"app_id='{self._game_id}' AND (session_id  BETWEEN '{next_slice[0]}' AND '{next_slice[-1]}'){ver_filter}"
            filt = f"app_id='{self._game_id}' AND session_id  IN ({id_string}){ver_filter}"
            db_name = self._settings["db_config"]["DB_NAME_DATA"]
            table_name = self._settings["db_config"]["TABLE"]
            data = SQL.SELECT(cursor      =self._db_cursor,             db_name       =db_name, table=table_name,
                              columns     =None,                        filter        =filt,
                              sort_columns=["session_id", "session_n"], sort_direction="ASC",)
            return data if data != None else []
            # self._select_queries.append(select_query) # this doesn't appear to be used???
        else:
            Logger.Log(f"Could not get data for {len(id_list)} sessions, MySQL connection is not open.", logging.WARN)
            return []

    def _allIDs(self) -> List[int]:
        if not self._db_cursor == None:
            # filt = f"app_id='{self._game_id}' AND (session_id  BETWEEN '{next_slice[0]}' AND '{next_slice[-1]}'){ver_filter}"
            db_name = self._settings["db_config"]["DB_NAME_DATA"]
            table_name = self._settings["db_config"]["TABLE"]
            filt = f"`app_id`='{self._game_id}'"
            data = SQL.SELECT(cursor  =self._db_cursor, db_name =db_name, table   =table_name,
                              columns =['session_id'],  filter  =filt,    distinct=True)
            return [int(id[0]) for id in data] if data != None else []
            # self._select_queries.append(select_query) # this doesn't appear to be used???
        else:
            Logger.Log(f"Could not get list of all session ids, MySQL connection is not open.", logging.WARN)
            return []

    def _fullDateRange(self) -> Dict[str,datetime]:
        if not self._db_cursor == None:
            # filt = f"app_id='{self._game_id}' AND (session_id  BETWEEN '{next_slice[0]}' AND '{next_slice[-1]}'){ver_filter}"
            db_name = self._settings["db_config"]["DB_NAME_DATA"]
            table_name = self._settings["db_config"]["TABLE"]
            # prep filter strings
            filt = f"`app_id`='{self._game_id}'"
            # run query
            result = SQL.SELECT(cursor=self._db_cursor, db_name=db_name, table=table_name,
                                columns=['MIN(server_time)', 'MAX(server_time)'], filter=filt)
            return {'min':result[0][0], 'max':result[0][1]}
        else:
            Logger.Log(f"Could not get full date range, MySQL connection is not open.", logging.WARN)
            return {'min':datetime.now(), 'max':datetime.now()}

    def _IDsFromDates(self, min:datetime, max:datetime, versions: Union[List[int],None]=None) -> List[int]:
        if not self._db_cursor == None:
            # alias long setting names.
            db_name = self._settings["db_config"]["DB_NAME_DATA"]
            table_name = self._settings["db_config"]["TABLE"]
            start = min.isoformat()
            end = max.isoformat()
            # prep filter strings
            ver_filter = f" AND `app_version` in ({','.join([str(x) for x in versions])}) " if versions else ''
            filt = f"`app_id`=\"{self._game_id}\" AND `session_n`='0' AND (`server_time` BETWEEN '{start}' AND '{end}'){ver_filter}"
            # run query
            # We grab the ids for all sessions that have 0th move in the proper date range.
            session_ids_raw = SQL.SELECT(cursor=self._db_cursor, db_name=db_name, table=table_name,
                                    columns=["`session_id`"], filter=filt,
                                    sort_columns=["`session_id`"], sort_direction="ASC", distinct=True)
            return [sess[0] for sess in session_ids_raw]
        else:
            Logger.Log(f"Could not get session list for {min.isoformat()}-{max.isoformat()} range, MySQL connection is not open.", logging.WARN)
            return []

    def _datesFromIDs(self, id_list:List[int], versions: Union[List[int],None]=None) -> Dict[str, datetime]:
        if not self._db_cursor == None:
            # alias long setting names.
            db_name = self._settings["db_config"]["DB_NAME_DATA"]
            table_name = self._settings["db_config"]["TABLE"]
            # prep filter strings
            ids_string = ','.join([f"'{x}'" for x in id_list])
            ver_filter = f" AND `app_version` in ({','.join([str(x) for x in versions])}) " if versions else ''
            filt = f"`app_id`='{self._game_id}' AND `session_id` IN ({ids_string}){ver_filter}"
            # run query
            result = SQL.SELECT(cursor=self._db_cursor, db_name=db_name, table=table_name,
                                columns=['MIN(server_time)', 'MAX(server_time)'], filter=filt)
            return {'min':result[0][0], 'max':result[0][1]}
        else:
            Logger.Log(f"Could not get date range for {len(id_list)} sessions, MySQL connection is not open.", logging.WARN)
            return {'min':datetime.now(), 'max':datetime.now()}
