import math
R=1000.0; C=100e-9; f=2000.0; A=1.0
w=2*math.pi*f
fc=1/(2*math.pi*R*C)
x=w*R*C
gain=1/math.sqrt(1+x*x)
ph=-math.degrees(math.atan(x))
print("fc =",fc)
print("wRC =",x)
print("theory gain =",gain)
print("theory phase_deg =",ph)
print("theory amp =",A*gain)
# measured
gm=0.6214528130301648; pm=-51.57825257958607; am=0.6194584914299128
print("gain err abs =",gm-gain, "rel% =",(gm-gain)/gain*100)
print("phase err abs deg =",pm-ph)
print("amp err abs =",am-A*gain,"rel% =",(am-A*gain)/(A*gain)*100)
# from peak max
print("max amp ratio =",0.690089512/0.997640766)
