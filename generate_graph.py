import sys
import random
if len(sys.argv) < 2:
    print >>sys.stderr, "Usage %s nodes tier_links peer_links"%(sys.argv[0])
    sys.exit(1)
nnodes = eval(sys.argv[1])
tier_links = eval(sys.argv[2])
peer_links = eval(sys.argv[3])
tier_nodes = {}
node_so_far = 0
for i in xrange(0, len(nnodes)):
    tier_nodes[i] = map(lambda k: k + node_so_far, range(0, nnodes[i]))
    node_so_far = tier_nodes[i][-1] + 1
for i in xrange(0, len(tier_links)):
    for node in tier_nodes[i]:
        other_nodes = random.sample(tier_nodes[i + 1], tier_links[i])
        for on in other_nodes:
            print "%d %d p2c"%(node, on)
            print "%d %d c2p"%(on, node)
peered = []
for i in xrange(0, len(peer_links)):
    for node in tier_nodes[i]:
        other_nodes = random.sample(filter(lambda k: k != node, tier_nodes[i]), peer_links[i])
        for on in other_nodes:
            if (node, on) not in peered:
                print "%d %d p2p"%(node, on)
                print "%d %d p2p"%(on, node)
                peered.append((node, on))
                peered.append((on, node))

