from structura_render.packets import polygon_packets, textured_packets


def prepare_geometry(data, *, position=(0, 0, 0)):
    packets = [packet for mesh in data['meshes'] for packet in textured_packets(mesh)]
    for points, faces, color in data['flat']:
        if len(faces):
            width = int(faces[0])
            packets.extend(polygon_packets(points, faces.reshape(-1, width + 1)[:, 1:],
                                           'OPAQUE' if color[3] == 255 else 'BLEND', color=color))
    for solid, points, faces, colors in data.get('colored', ()):
        packets.extend(polygon_packets(points, faces.reshape(-1, 4)[:, 1:],
                                       'OPAQUE' if solid else 'BLEND', colors=colors, cull=solid))
    result = {key: value for key, value in data.items() if key not in ('meshes', 'flat', 'colored', 'layers')}
    result['packets'] = packets
    result['position'] = position
    result['layers'] = {name: prepare_geometry(layer, position=position) for name, layer in data.get('layers', {}).items()}
    images = {packet.texture_key: packet.image.nbytes for packet in packets if packet.image is not None}
    result['geometry_bytes'] = (sum(packet.nbytes for packet in packets) + sum(images.values())
                                + sum(layer['geometry_bytes'] for layer in result['layers'].values()))
    return result
