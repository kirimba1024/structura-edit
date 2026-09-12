from io import BytesIO
import zipfile

import numpy as np


def encode_arrays(**arrays):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, array in arrays.items():
            with archive.open(name + '.npy', 'w', force_zip64=True) as entry:
                np.lib.format.write_array(entry, np.asanyarray(array), allow_pickle=False)
    return stream.getvalue()
