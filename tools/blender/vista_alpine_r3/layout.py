"""Shared metre-based Alpine landform, shoreline and connected walking route."""
import math

WATER_Z=-4.0
LAKE=(-210.0,75.0,175.0,155.0)
NEAR=(-500.0,300.0,-400.0,600.0)
ROUTE=[(4.7,16),(-2,22),(-16,28),(-25,44),(-20,65),(2,92),(36,115),
       (65,106),(82,75),(64,42),(38,26),(4.7,16)]

def smooth(t):
    t=max(0.,min(1.,t));return t*t*(3-2*t)

def noise(x,y):
    ix,iy=math.floor(x),math.floor(y);a,b=smooth(x-ix),smooth(y-iy)
    def point(i,j):
        n=(i*374761393+j*668265263+91026)&0xffffffff
        n=((n^(n>>13))*1274126177)&0xffffffff
        return (n^(n>>16))/4294967295.0
    p=point(ix,iy)*(1-a)+point(ix+1,iy)*a
    q=point(ix,iy+1)*(1-a)+point(ix+1,iy+1)*a
    return p*(1-b)+q*b

def fractal(x,y):
    return sum((noise(x*2**i,y*2**i)-.5)*.52**i for i in range(5))

def lake_radius(x,y):
    cx,cy,rx,ry=LAKE;u,v=(x-cx)/rx,(y-cy)/ry;t=math.atan2(v,u)
    return math.hypot(u,v)/(1+.035*math.sin(3*t+.2)+.02*math.sin(7*t-.8))

def height(x,y):
    radius=lake_radius(x,y)
    low=WATER_Z-24*smooth((1-radius)/.55)
    meadow=5*smooth((radius-1.0)/.38)+1.8*fractal(x/65,y/65)*smooth((radius-1.0)/.20)
    distant=0
    for cx,cy,h,sx,sy in [(-780,430,700,380,470),(-310,1120,1080,470,390),
                          (610,900,930,510,440),(1200,-290,630,520,570),
                          (-1230,-790,920,510,490),(-1000,1550,740,500,430)]:
        u=(x-cx+90*fractal(x/350,y/350))/sx
        v=(y-cy+70*fractal((x+300)/400,(y-100)/400))/sy
        mass=h*math.exp(-(u*u+v*v)*1.35)
        ridge=.82+.55*abs(fractal(x/140+2,y/140-1))
        distant=max(distant,mass*ridge)
    distant*=smooth((math.hypot((x+120)*.9,y-80)-270)/430)
    # Rolling physical foothills sit in front of the photographic far skyline.
    distant=140*math.tanh(distant/420)
    z=low+meadow+distant
    pad=max(max(-14-x,0,x-28),max(-10-y,0,y-24))
    return -.20+(z+.20)*smooth(pad/24)

def route_distance(x,y):
    best=1e9
    for (ax,ay),(bx,by) in zip(ROUTE,ROUTE[1:]):
        dx,dy=bx-ax,by-ay;t=max(0.,min(1.,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy)))
        best=min(best,math.hypot(x-ax-t*dx,y-ay-t*dy))
    return best

def slope(x,y):
    return math.hypot(height(x+.5,y)-height(x-.5,y),height(x,y+.5)-height(x,y-.5))
