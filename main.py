import copy

import numpy
from numpy.random import gumbel
from random import random

header = '''
o Box{}'''

vert = '''
v {}
v {}
v {}
v {}
v {}
v {}
v {}
v {}'''

normals = '''
vn -1.0 0.0 0.0
vn -1.0 0.0 0.0
vn 1.0 0.0 0.0
vn 1.0 -0.0 0.0
vn 0.0 -1.0 0.0
vn 0.0 -1.0 0.0
vn 0.0 1.0 0.0
vn 0.0 1.0 0.0
vn 0.0 0.0 -1.0
vn 0.0 0.0 -1.0
vn 0.0 0.0 1.0
vn 0.0 0.0 1.0'''

faces_vert = [1, 2, 3,
              3, 2, 4,
              5, 6, 7,
              5, 7, 8,
              6, 5, 1,
              1, 5, 2,
              8, 7, 3,
              8, 3, 4,
              3, 7, 1,
              1, 7, 6,
              8, 4, 2,
              8, 2, 5]

faces = '''
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{} 
f {}//{} {}//{} {}//{}'''

clean_box = [[0.0, 0.0, 0.0],
[0.0, 0.0, 1.0],
[0.0, 1.0, 0.0],
[0.0, 1.0, 1.0],
[1.0, 0.0, 1.0],
[1.0, 0.0, 0.0],
[1.0, 1.0, 0.0],
[1.0, 1.0, 1.0]]

def scale_x(data, s):
    new_data = []
    for v in data:
        if v[0] == 1:
            v[0] = v[0]*s
        new_data.append(v)
    return new_data

def scale_y(data, s):
    new_data = []
    for v in data:
        if v[1] == 1:
            v[1] = v[1]*s
        new_data.append(v)
    return new_data

def scale_z(data, s):
    new_data = []
    for v in data:
        if v[2] == 1:
            v[2] = v[2]*s
        new_data.append(v)
    return new_data

def translate_x(data, trans):
    new_data = []
    for v in data:
        v[0] = v[0]+trans
        new_data.append(v)
    return new_data

def translate_y(data, trans):
    new_data = []
    for v in data:
        v[1] = v[1]+trans
        new_data.append(v)
    return new_data

def translate_z(data, trans):
    new_data = []
    for v in data:
        v[2] = v[2]+trans
        new_data.append(v)
    return new_data

def list_to_str(data):
    new_data = []
    for v in data:
        tmp = [str(x) for x in v]
        new_data.append(' '.join(tmp))
    return new_data

def create_faces(cube_idx):
    data = []
    count = 1+cube_idx*12
    for i, v in enumerate(faces_vert):
        data.append(v+cube_idx*8)
        data.append(count)
        if i % 3 == 2:
            count += 1
    data = faces.format(*data)
    return data

def make_box(sca, pos, i):
    sx = sca[0]
    sy = sca[1]
    sz = sca[2]
    x = pos[0]
    y = pos[1]
    z = pos[2]
    data = copy.deepcopy(clean_box)
    data = scale_x(data, sx)
    data = scale_y(data, sy)
    data = scale_z(data, sz)
    data = translate_x(data, x)
    data = translate_y(data, y)
    data = translate_z(data, z)
    data = list_to_str(data)
    ff = create_faces(i)
    cube = header.format(i) + vert.format(*data) + normals + ff
    return cube

def main():

    ### OPTIONS
    #width of base x-axis in mm
    base_x = 30
    #width of base y-axis in mm
    base_y = 28
    #factor determining the decrease in size of buildings near edge
    size_drop_off = 0.8
    #factor determining the increase in spacing between building near edge
    spacing_drop_off = 1.1
    #INT number of buildings to place on x
    x_num = 10
    #INT number of buildings to place on y
    y_num = 10
    ###

    base = make_box([base_x, base_y, 1], [0, 0, 0], 0)
    cubes = []
    count = 0
    dec = numpy.linspace(1.2, size_drop_off, x_num*y_num)
    inc = numpy.linspace(1.0, spacing_drop_off, x_num*y_num)
    for i in range(0, x_num):
        for j in range(0, y_num):
            scales = [dec[count]*(2+gumbel(scale=1)),
                      dec[count]*(2+gumbel(scale=1)),
                      dec[count]*(2+gumbel(scale=1))]
            origin = [inc[count]*i*(2.5+(random()-0.5)), inc[count]*j*(2.5+(random()-0.5)), 0]
            cube = make_box(scales, origin, count)
            cubes.append(cube)
            count += 1

    to_write = base + ''.join(cubes)

    with open('./cube.obj', 'w') as f:
        f.write(to_write)

if __name__ == '__main__':
    main()