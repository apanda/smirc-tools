import sys
if len(sys.argv) < 2:
    print >>sys.stderr, "Usage: %s file"%(sys.argv[0])
    sys.exit(1)
f = open(sys.argv[1])
# discard first line
p = f.readline().split()[2:]
dests = []
classes = []
for d in p:
    dests.append(d)
    classes.append({'0': 0, '1': 0, '2':0, '3':0, '4':0})
total_links = 0
for l in f:
    total_links += 1
    p = l.split()[2:]
    for idx in xrange(0, len(p)):
        classes[idx][p[idx]] += 1
totalf = float(total_links)
totalf = 1.0
for idx in xrange(0, len(dests)):
    print "%s %f %f %f %f"%(dests[idx], float(classes[idx]['1'])/totalf, float(classes[idx]['2'])/totalf, float(classes[idx]['3'])/totalf, float(classes[idx]['4'])/totalf)
    
