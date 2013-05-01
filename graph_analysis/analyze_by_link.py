import sys
if len(sys.argv) < 2:
    print >>sys.stderr, "Usage: %s file"%(sys.argv[0])
    sys.exit(1)
f = open(sys.argv[1])
# discard first line
f.readline()
for l in f:
    classes = {'0': 0, '1': 0, '2':0, '3':0, '4':0}
    total = 0
    p = l.split()[2:]
    for k in p:
        classes[k] += 1
        total +=1 
    p = l.split()
    total = 1
    print "%s %s %f %f %f %f"%(p[0], p[1], float(classes['1'])/float(total), float(classes['2'])/float(total), float(classes['3'])/float(total), float(classes['4'])/float(total))
