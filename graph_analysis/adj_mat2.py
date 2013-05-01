import sys
if len(sys.argv) < 3:
    print >>sys.stderr, "adjacency_matrix.py topology result_file"
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

#for i in links[as_rev_map[190]]:
#    print "%s(%s) %s(%s)"%(as_map[as_rev_map[190]], as_rev_map[as_map[as_rev_map[190]]], i, as_map[i])
f.close()
f = open(sys.argv[2])
# Transform line 1
l = f.readline()
p = l.split()
def transform(s):
    if s.isdigit():
        return str(as_rev_map[int(s)])
    else:
        return s
np = map(transform, p)
print ' '.join(np)
# Do the rest
for l in f:
    p = l.split()
    print "%s "% transform(p[0]),
    print "%s "%transform(p[1]),
    print ' '.join(p[2:])
    
