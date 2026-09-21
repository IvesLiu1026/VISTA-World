"""Reviewed navigation anchors. Models never output coordinates or routes."""
import heapq
import math


def entity(state, short_id):
    return next(e for e in state['entities'] if e['short_id'] == short_id)


def route(state, destination):
    graph = {}; places = {}

    def chain(points):
        for point in points:
            graph.setdefault(tuple(point), set())
        for a, b in zip(points, points[1:]):
            graph[tuple(a)].add(tuple(b)); graph[tuple(b)].add(tuple(a))

    room = state.get('micro_room')
    if room:
        ox, oy, oz = room['origin_cm']; sign = -1 if room['arrangement'] == 1 else 1
        def point(x, y): return (ox+sign*x, oy+sign*y, oz+86)
        ring = [point(x, y) for x, y in [(160,160),(210,160),(210,-185),(75,-185),(75,160),(160,160)]]
        chain(ring); places.update(center=ring[0], window=ring[2])
        phone = entity(state, 'phone')['position_cm']
        px, py = sign*(phone[0]-ox), sign*(phone[1]-oy)
        cy, margin = {'lounge': (5,65), 'study': (80,105), 'bedroom': (145,55)}[room['family']]
        cy += 18 if room['arrangement'] == 2 else 0
        y = cy+(margin if py>cy else -margin)
        approach = [(75,160),(75,y),(px,y)]
        if room['family'] == 'bedroom':
            approach = [(75,160),(75,210),(-260,210),(-260,py),(px-55,py)]
        points = [point(x,y) for x,y in approach]; chain(points); places['phone'] = points[-1]
    else:
        def floor(points,z): return [(x,y,z) for x,y in points]
        lower = floor([(1147,-1071),(1200,-1000),(1260,-1000),(1260,-830),
                       (1105,-830),(1105,-790),(1002,-790),(1002,-700)],86)
        upper = floor([(1410,-710),(1260,-730),(470,-740),(470,-900),(450,-1030),(382,-1082)],406)
        chain(lower+[(1230,-700,86),(1230,-50,246),(1410,-50,246)]+upper)
        chain(floor([(1002,-700),(950,-500),(950,-290),(1130,-290),(1130,-200)],86))
        chain(floor([(950,-290),(805,-265),(680,-265),(440,-290),(440,-410),(284,-415)],86))
        chain(floor([(1200,-1000),(1200,-925),(1150,-925)],86))
        chain(floor([(382,-1082),(375,-1058)],406))
        chain(floor([(1260,-730),(1260,-900),(1245,-1015),(1250,-990)],406))
        # Native-reviewed viewing space beside the tub. Keep the tap's operating
        # position free for the companion; this is human staging, not AI success.
        chain(floor([(1245,-1015),(1285,-1010),(1285,-1100)],406))
        chain(floor([(1260,-730),(1000,-730),(1000,-900),(850,-900),(820,-940)],406))
        places.update(entry_hall=(1130,-200,86),living_room=(440,-290,86),
            kitchen_dining=(1147,-1071,86),bedroom=(382,-1082,406),phone=(382,-1082,406),
            office=(820,-940,406),bathroom_laundry=(1285,-1100,406))
    if destination not in places:
        raise ValueError('Destination unavailable in the active scene')
    start = min(graph, key=lambda p: math.dist(p,state['player_cm']))
    if math.dist(start,state['player_cm']) > 110:
        raise RuntimeError('Human left the supported route; stop and replay from scene entry')
    goal = places[destination]; queue = [(0,start,[])]; visited=set()
    while queue:
        cost,node,path=heapq.heappop(queue)
        if node in visited: continue
        visited.add(node); path=path+[node]
        if node==goal:
            return [list(p) for p in path]
        for nxt in sorted(graph[node]):
            heapq.heappush(queue,(cost+math.dist(node,nxt),nxt,path))
    raise RuntimeError('No supported route to destination')
