from weakref import WeakValueDictionary

import pyvista as pv


class TexturePool:
    def __init__(self):
        self.textures = WeakValueDictionary()

    def get(self, packet):
        texture = self.textures.get(packet.texture_key)
        if texture is None:
            texture = pv.Texture(packet.image)
            texture.SetInterpolate(False)
            texture.mipmap = False
            self.textures[packet.texture_key] = texture
        return texture


def texture_pool(plotter):
    pool = getattr(plotter, '_structura_textures', None)
    if pool is None:
        pool = plotter._structura_textures = TexturePool()
    return pool
