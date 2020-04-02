# -*- coding: utf-8 -*-
from __init__ import BASEDIR, SETTINGS
import networkx as nx
import networkit as nkit
from yaml import safe_load
from os import path
import rtree
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape, LineString, Point
from shapely import ops


def flood_layer_union(flood_layer):
    # TODO: rewrite docstring -> fix..
    """Fix geometry to calculate difference overlay with border layer. Needed to select flooded amenities"""

    flood_geom = []
    for poly in range(len(flood_layer)):
        if flood_layer['geometry'][poly] is not None:
            flood_geom.append(shape(flood_layer['geometry'][poly]))
    union_l = ops.cascaded_union(flood_geom)

    # TODO: here geodataframe needed?
    df = pd.DataFrame(union_l, columns=['geometry'])
    geodf = gpd.GeoDataFrame(df, geometry='geometry')

    return geodf


def flood_intersection(graph, flood_layer, output):
    """
        Intersects network routing graph with flood polygons and removes edges and nodes which are affected by flood.
        :param graph: graph of complete area
        :type graph: osmnx or networkx network routing graph with edge and node file
        :param flood_layer: areas which are flooded
        :type flood_layer: polygon shapefile
        :param output: folder path to save output
        :type output: string
        :return: flood networkx graph
        """
    flood_data = flood_layer_union(flood_layer)

    edge_data = list(graph.edges(data=True))

    # create an empty spatial index object
    index = rtree.index.Index()
    counter = 0
    for edge in range(len(edge_data)):
        edge_geom = shape(LineString([Point(edge_data[edge][0]), Point(edge_data[edge][1])]))
        index.insert(counter, edge_geom.bounds)
        counter += 1

    # check intersection and remove affected nodes
    intersect_counter = 0
    for poly in flood_data['geometry']:
        for fid in list(index.intersection(shape(poly).bounds)):
            edge_geom_shape = shape(LineString([Point(edge_data[fid][0]), Point(edge_data[fid][1])]))
            if edge_geom_shape.intersects(shape(poly)):
                e = edge_data[fid][0]
                e_to = edge_data[fid][1]
                # remove intersected edges
                if graph.has_edge(e, e_to):
                    graph.remove_edge(e, e_to)
                # remove intersected nodes
                if Point(edge_data[fid][0]).intersects(shape(poly)) and graph.has_node(e):
                    graph.remove_node(e)
                    intersect_counter += 1
                if Point(edge_data[fid][1]).intersects(shape(poly)) and graph.has_node(e_to):
                    graph.remove_node(e_to)
                    intersect_counter += 1
    print('Amount of intersected and removed nodes:', intersect_counter)

    # save networkx graph with complete graph enum_id
    try:
        nx.write_shp(graph, output)
    except Exception as err:
        print(err)
    print('Intersected networkx graph saved')

    return graph


def create_weighted_graph(nx_graph):
    """Create weighted and directed NetworKit graph. Weight is defined by needed travel duration for each road by
    km / speed limit.
    :param nx_graph: Networkx graph with information about road type and road length
    :return: Weighted and directed NetworKit graph
    """
    # convert to weighted and directed NetworKit graph
    nkit_graph = nkit.nxadapter.nx2nk(nx_graph)
    nkit_edges = nkit_graph.edges()
    graph_weighted_directed = nkit.Graph(nkit_graph.numberOfNodes(), weighted=True, directed=True)

    # Openrouteservice yaml file with defined speed limits for each road type
    speed_limit = safe_load(open(path.join(BASEDIR, SETTINGS['speed_limits'])))

    for edge, highway, length in zip(nkit_edges, [w[2] for w in nx_graph.edges.data('highway')],
                                     [float(w[2]) for w in nx_graph.edges.data('length')]):
        try:
            weight = (length / 1000) / speed_limit[highway]
        except KeyError:
            # in some cases two road types are defined for one road -> take the first one
            weight = (length / 1000) / speed_limit[highway.strip('][').split('\'')[1]]

        # add edges and weight to new, empty nkit graph
        graph_weighted_directed.addEdge(edge[0], edge[1], weight)

    nkit.overview(graph_weighted_directed)

    print('Created weighted NetworKit graph.')
    return graph_weighted_directed
