import sys
if len(sys.argv) < 2:
    print >>sys.stderr, "adjacency_matrix.py topology"
    sys.exit(1)
f = open(sys.argv[1])
as_assigned = 1
as_map = {}
as_rev_map = {}
links = {}
link_map = {}
link_rev_map = {}
relationship = {}
relationships = {}
for l in f:
    p = l.strip().split()
    if p[0] not in as_map:
        as_map[p[0]] = as_assigned
        as_rev_map[as_assigned] = p[0]
        as_assigned += 1
    if p[1] not in as_map:
        as_map[p[1]] = as_assigned
        as_rev_map[as_assigned] = p[1]
        as_assigned += 1
    if p[0] not in links:
        links[p[0]] = []
        relationship[p[0]] = {}
        relationships[p[0]] = {'p2p': [], 'c2p': [], 'p2c': []}
        link_rev_map[p[0]] = {}
        link_map[p[0]] = {}
        link_rev_map[p[0]] = {}
    links[p[0]].append(p[1])
    link_map[p[0]][p[1]] = len(links[p[0]])
    link_rev_map[p[0]][link_map[p[0]][p[1]]] = p[1] 
    relationship[p[0]][p[1]] = p[2]
    relationships[p[0]][p[2]].append(p[1])
obj = {}
obj['AdjacencyMatrix'] = {}
for k in sorted(as_rev_map.keys()):
    v = k
    k = as_rev_map[v]
    adj = map(lambda l: as_map[l], links[k])
    adj.append(v)
    adj.sort()
    obj['AdjacencyMatrix'][str(v)] = adj
obj['PortToNodeMap'] = {}
obj['NodeToPortMap'] = {}
for k in sorted(as_rev_map.keys()):
    v = k
    k = as_rev_map[v]
    obj['PortToNodeMap'][str(v)] = [v]
    obj['NodeToPortMap'][str(v)] = {str(v):0}
    port = 1
    for link in links[k]:
        obj['PortToNodeMap'][str(v)].append(as_map[link])
        obj['NodeToPortMap'][str(v)][str(as_map[link])] = port
        port += 1
        #print "%d %d"%(v, as_map[link])
obj['ExportTables'] = {}
# Link 0 is always the link to self
for k in sorted(as_rev_map.keys()):
    v = k
    k = as_rev_map[v]
    # Row 0
    obj['ExportTables'][str(v)] = [[1]]
    for i in links[k]:
        obj['ExportTables'][str(v)][0].append(0)
    #other rows
    for i in links[k]:
        export = [1]
        rel = relationship[k][i]
        for j in links[k]:
            if j == i:
                export.append(0)
            elif rel == 'p2p':
                if relationship[k][j] == 'p2c':
                    export.append(1)
                else:
                    export.append(0)
            elif rel == 'p2c':
                export.append(1)
            elif rel == 'c2p':
                if relationship[k][j] == 'p2c':
                    export.append(1)
                else:
                    export.append(0)
        obj['ExportTables'][str(v)].append(export)
obj['IndicesLink'] = {}
obj['IndicesNode'] = {}
#ordering clients then peers then providers
for k in sorted(as_rev_map.keys()):
    v = k
    k = as_rev_map[v]
    print >>sys.stderr, str(v)
    obj['IndicesNode'][str(v)] = [v]
    obj['IndicesLink'][str(v)] = [0]
    for n in relationships[k]['p2c']:
        obj['IndicesNode'][str(v)].append(as_map[n])
        obj['IndicesLink'][str(v)].append(link_map[k][n])
    for n in relationships[k]['p2p']:
        obj['IndicesNode'][str(v)].append(as_map[n])
        obj['IndicesLink'][str(v)].append(link_map[k][n])
    for n in relationships[k]['c2p']:
        obj['IndicesNode'][str(v)].append(as_map[n])
        obj['IndicesLink'][str(v)].append(link_map[k][n])




import json
print json.dumps(obj)
