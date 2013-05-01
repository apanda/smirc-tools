import sys
if len(sys.argv) < 2:
    print >>sys.stderr, "Usage: %s file"%(sys.argv[0])
    sys.exit(1)
f = open(sys.argv[1])
# discard first line
f.readline()
classes = {'0': 0, '1': 0, '2':0, '3':0, '4':0}
total = 0
for l in f:
    p = l.split()[2:]
    for k in p:
        classes[k] += 1
        total +=1
for k in sorted(classes.keys()):
    print "%s %f"%(k, float(classes[k])/float(total))

