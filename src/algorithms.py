import logging
import random
from datetime import datetime
from typing import List

import cplex
import numpy as np
import scipy.cluster.vq as vq

from base_station import BaseStation
from edge_server import EdgeServer
from utils import DataUtils


class ServerPlacement(object):
    def __init__(self, base_stations: List[BaseStation], distances: List[List[float]]):
        self.base_stations = base_stations.copy()
        self.distances = distances
        self.edge_servers = None

    def place_server(self, edge_server_num):
        raise NotImplementedError

    def _distance_edge_server_base_station(self, edge_server: EdgeServer, base_station: BaseStation) -> float:
        """
        Calculate distance between given edge server and base station
        
        :param edge_server: 
        :param base_station: 
        :return: distance(km)
        """
        if edge_server.base_station_id:
            return self.distances[edge_server.base_station_id][base_station.id]
        return DataUtils.calc_distance(edge_server.latitude, edge_server.longitude, base_station.latitude,
                                       base_station.longitude)

    def objective_latency(self):
        """
        Calculate average edge server access delay
        """
        assert self.edge_servers
        total_delay = 0
        base_station_num = 0
        for es in self.edge_servers:
            for bs in es.assigned_base_stations:
                delay = self._distance_edge_server_base_station(es, bs)
                logging.debug("base station={0}  delay={1}".format(bs.id, delay))
                total_delay += delay
                base_station_num += 1
        return total_delay / base_station_num

    def objective_workload(self):
        """
        Calculate average edge server workload
        
        Max worklaod of edge server - Min workload
        """
        assert self.edge_servers
        workloads = [e.workload for e in self.edge_servers]
        logging.debug("standard deviation of workload" + str(workloads))
        res = np.std(workloads)
        return res


class MIPServerPlacement(ServerPlacement):
    def setupup_problem(self, c):
        c.objective.set_sense(c.objective.sense.minimize)

        c.linear_constraints.add()

    def preprocess_problem(self, k):
        # 每个基站，找出距离它最近的N/K个基站
        d = np.array(self.distances)
        cap = int(len(self.base_stations)/k)
        assign = []
        for i, row in enumerate(d):
            indices = row.argpartition(cap)[:cap]
            assign.append(indices.tolist())
            logging.debug("Found nearest {0} base stations of base station {1}".format(cap, i))


        pass

    def place_server(self, edge_server_num):
        self.preprocess_problem(edge_server_num)

        c = cplex.Cplex

        self.setupup_problem(c)
        pass


class KMeansServerPlacement(ServerPlacement):
    """
    K-means approach
    """

    def place_server(self, edge_server_num):
        logging.info("{0}:Start running k-means".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        # init data as ndarray
        base_stations = self.base_stations
        coordinates = list(map(lambda x: (x.latitude, x.longitude), base_stations))
        data = np.array(coordinates)
        k = edge_server_num

        # k-means
        centroid, label = vq.kmeans2(data, k, iter=100, minit='points')

        # process result
        edge_servers = [EdgeServer(i, row[0], row[1]) for i, row in enumerate(centroid)]
        for bs, es in enumerate(label):
            edge_servers[es].assigned_base_stations.append(base_stations[bs])
            edge_servers[es].workload += base_stations[bs].workload

        self.edge_servers = list(filter(lambda x: x.workload != 0, edge_servers))
        logging.info("{0}:End running k-means".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))


class TopKServerPlacement(ServerPlacement):
    """
    Top-K approach
    """

    def place_server(self, edge_server_num):
        logging.info("{0}:Start running Top-k".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        sorted_base_stations = sorted(self.base_stations, key=lambda x: x.workload, reverse=True)
        edge_servers = [EdgeServer(i, item.latitude, item.longitude, item.id) for i, item in
                        enumerate(sorted_base_stations[:edge_server_num])]
        for i, base_station in enumerate(sorted_base_stations):
            closest_edge_server = None
            min_distance = 1e10
            for j, edge_server in enumerate(edge_servers):
                tmp = self._distance_edge_server_base_station(edge_server, base_station)
                if tmp < min_distance:
                    min_distance = tmp
                    closest_edge_server = edge_server
            closest_edge_server.assigned_base_stations.append(base_station)
            closest_edge_server.workload += base_station.workload
        self.edge_servers = edge_servers
        logging.info("{0}:End running Top-k".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))


class RandomServerPlacement(ServerPlacement):
    """
    Random approach
    """

    def place_server(self, edge_server_num):
        base_stations = self.base_stations
        logging.info("{0}:Start running Random".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        random_base_stations = random.sample(self.base_stations, edge_server_num)
        edge_servers = [EdgeServer(i, item.latitude, item.longitude, item.id) for i, item in
                        enumerate(random_base_stations)]
        for i, base_station in enumerate(base_stations):
            closest_edge_server = None
            min_distance = 1e10
            for j, edge_server in enumerate(edge_servers):
                tmp = self._distance_edge_server_base_station(edge_server, base_station)
                if tmp < min_distance:
                    min_distance = tmp
                    closest_edge_server = edge_server
            closest_edge_server.assigned_base_stations.append(base_station)
            closest_edge_server.workload += base_station.workload
        self.edge_servers = edge_servers
        logging.info("{0}:End running Random".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
