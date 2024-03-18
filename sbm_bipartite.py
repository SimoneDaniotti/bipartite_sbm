import graph_tool.all as gt
import numpy as np
import random
import pandas as pd
import pickle

def cols2bipartite(file):
    # Read DataFrame from CSV file
    df = pd.read_csv(file)  # Replace 'your_file.csv' with the actual filename

    # Constructing the dictionary
    # mapping_dict = {}
    # for index, row in df.iterrows():
    #     mapping_dict[row[0]] = 0  # Assuming the first column is Column1
    #     mapping_dict[row[1]] = 1  # Assuming the second column is Column2

    #  Get unique values from column 0 and column 1
    unique_values_col0 = df.iloc[:, 0].unique()
    unique_values_col1 = df.iloc[:, 1].unique()

    # Constructing the dictionary
    mapping_dict = {val: 0 for val in unique_values_col0}
    mapping_dict.update({val: 1 for val in unique_values_col1})

    return mapping_dict


def cols2multipartite(file):
    ##! build the mapping dict from node to its layer_index
    df = pd.read_csv(file)  # Replace 'your_file.csv' with the actual filename
    mapping_dict = pd.Series(df[df.columns[0]].values,index=df[df.columns[1]]).to_dict()
    return mapping_dict



class bipartite_sbm():
    '''
    Class for topic-modeling with sbm's.
    '''

    def __init__(self):
        self.g = None ## network

        # self.words = [] ## list of word nodes
        # self.documents = [] ## list of document nodes

        self.state = None ## inference state from graphtool
        self.groups = {} ## results of group membership from inference
        self.mdl = np.nan ## minimum description length of inferred state
        self.L = np.nan ## number of levels in hierarchy

    def load_graph(self,path):
        self.g=gt.load_graph_from_csv(path,hashed=True,skip_first=True,eprop_types=["int"])
        d=cols2bipartite(path)
        kind = self.g.new_vp("int")     # creates a VertexPropertyMap of type string
        for v in self.g.vertices():
            kind[v] = d[self.g.vp.name[v]]
        self.g.vp.kind = kind




    def load_multipartite_graph(self,path,layer_map_path):
        ##! load a multipartite graph; the "layer_map_path" is the csv file that project the node to its layer_index

        self.g=gt.load_graph_from_csv(path,hashed=True,skip_first=True,eprop_types=["int"])
        d=cols2multipartite(layer_map_path)
        kind = self.g.new_vp("int")     # creates a VertexPropertyMap of type string
        for v in self.g.vertices():
            kind[v] = d[self.g.vp.name[v]]
        self.g.vp.kind = kind



    def save_graph(self,filename = 'graph.gt.gz'):
        '''
        Save the word-document network generated by make_graph() as filename.
        Allows for loading the graph without calling make_graph().
        '''
        self.g.save(filename)

    # def load_graph(self,filename = 'graph.gt.gz'):
    #     '''
    #     Load a word-document network generated by make_graph() and saved with save_graph().
    #     '''
    #     self.g = gt.load_graph(filename)
    #     self.words = [ self.g.vp['name'][v] for v in  self.g.vertices() if self.g.vp['kind'][v]==1   ]
    #     self.documents = [ self.g.vp['name'][v] for v in  self.g.vertices() if self.g.vp['kind'][v]==0   ]


    def fit(self,overlap = False, n_init = 1, verbose=False, epsilon=1e-3):
        '''
        Fit the sbm to the word-document network.
        - overlap, bool (default: False). Overlapping or Non-overlapping groups.
            Overlapping not implemented yet
        - n_init, int (default:1): number of different initial conditions to run in order to avoid local minimum of MDL.
        '''
        g = self.g
        if g is None:
            print('No data to fit the SBM. Load some data first (make_graph)')
        else:
            if overlap and "count" in g.ep:
                raise ValueError("When using overlapping SBMs, the graph must be constructed with 'counts=False'")
            clabel = g.vp['kind']

            state_args = {'clabel': clabel, 'pclabel': clabel}
            if "count" in g.ep:
                state_args["eweight"] = g.ep.count

            ## the inference
            mdl = np.inf ##
            for i_n_init in range(n_init):
                base_type = gt.BlockState if not overlap else gt.OverlapBlockState
                state_tmp = gt.minimize_nested_blockmodel_dl(g,
                                                             state_args=dict(
                                                                 base_type=base_type,
                                                                 **state_args),
                                                             multilevel_mcmc_args=dict(
                                                                 verbose=verbose))
                L = 0
                for s in state_tmp.levels:
                    L += 1
                    if s.get_nonempty_B() == 2:
                        break
                state_tmp = state_tmp.copy(bs=state_tmp.get_bs()[:L] + [np.zeros(1)])
                # state_tmp = state_tmp.copy(sampling=True)
                # delta = 1 + epsilon
                # while abs(delta) > epsilon:
                #     delta = state_tmp.multiflip_mcmc_sweep(niter=10, beta=np.inf)[0]
                #     print(delta)
                print(state_tmp)

                mdl_tmp = state_tmp.entropy()
                if mdl_tmp < mdl:
                    mdl = 1.0*mdl_tmp
                    state = state_tmp.copy()

            self.state = state
            ## minimum description length
            self.mdl = state.entropy()
            L = len(state.levels)
            if L == 2:
                self.L = 1
            else:
                self.L = L-2

    def save_model(self, path):
        '''
        Save the trained model in the specified path as a pickle
        '''
        if '.pickle' not in path:
            path += '.pickle'
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        
    def load_model(self, path):
        '''
        Load the trained model from the specified path to the pickle file
        '''
        if '.pickle' not in path:
            path += '.pickle'
        with open(path, 'rb') as f:
            obj = pickle.load(f)
            self.__dict__.update(obj.__dict__)

    def load_graph_from_networkx(self, G_nx, nx_layer_index):
        ##! load_graph_from_networkx(G_nx, nx_layer_index), which could load graph from networkx G_nx; nx_layer_index is the string that identify the vertex layer

        self.g = gt.Graph()

        node_map = {v_nx: v for v, v_nx in enumerate(G_nx.nodes())}
        self.g.add_vertex(len(node_map))
        self.g.add_edge_list([(node_map[u], node_map[v]) for u, v in G_nx.edges()])

        for v_nx, v in node_map.items():
            self.g.vp.name[v] = v_nx

        kind = self.g.new_vp("int")     # creates a VertexPropertyMap of type string
        for v in self.g.vertices():
            kind[v] = G_nx.nodes[self.g.vp.name[v]][nx_layer_index]
        self.g.vp.kind = kind