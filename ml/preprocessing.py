"""One RGB letterbox/normalization path shared by cache, training and inference."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
from PIL import Image
import torch

from ml.data.deduplicate import stable_hash
from ml.data.extract_frames import display_transform, transformed_image


@dataclass(frozen=True)
class PreprocessConfig:
    version: str = "letterbox-imagenet-v1"
    size: int = 224
    channel_order: str = "RGB"
    mean: tuple = (.485,.456,.406)
    std: tuple = (.229,.224,.225)
    interpolation: str = "PIL-bilinear"
    padding_rgb: tuple = (0,0,0)

    def __post_init__(self):
        if (self.version!="letterbox-imagenet-v1" or self.size!=224 or self.channel_order!="RGB"
                or tuple(self.mean)!=(.485,.456,.406) or tuple(self.std)!=(.229,.224,.225)
                or self.interpolation!="PIL-bilinear" or tuple(self.padding_rgb)!=(0,0,0)):
            raise ValueError("unsupported preprocessing; semantic changes need a new implemented version")

    def descriptor(self):return asdict(self)

    def fingerprint(self):return stable_hash(self.descriptor())


def preprocess_image(image: Image.Image|np.ndarray, *, rotation: int=0,
                     config: PreprocessConfig=PreprocessConfig()) -> dict:
    if isinstance(image,np.ndarray):
        if image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
            raise ValueError("expected uint8 HWC RGB pixels, not normalized/BGR tensors")
        image=Image.fromarray(image)
    if (not isinstance(image,Image.Image) or image.mode not in ("RGB","L") or min(image.size)<=0
            or image.width*image.height>16777216):
        raise ValueError("expected a valid RGB/grayscale source image")
    original_width,original_height=image.size
    transform=display_transform({"width":original_width,"height":original_height,"rotation":rotation})
    rgb=transformed_image(image,transform)
    scale=min(config.size/rgb.width,config.size/rgb.height)
    width=max(1,min(config.size,round(rgb.width*scale)))
    height=max(1,min(config.size,round(rgb.height*scale)))
    left,top=(config.size-width)//2,(config.size-height)//2
    canvas=Image.new("RGB",(config.size,config.size),tuple(config.padding_rgb))
    canvas.paste(rgb.resize((width,height),Image.Resampling.BILINEAR),(left,top))
    array=np.array(canvas,dtype=np.float32)/255.0
    tensor=torch.from_numpy(array.transpose(2,0,1).copy())
    mean=torch.tensor(config.mean,dtype=torch.float32)[:,None,None]
    std=torch.tensor(config.std,dtype=torch.float32)[:,None,None]
    tensor=(tensor-mean)/std
    valid=torch.zeros((config.size,config.size),dtype=torch.bool)
    valid[top:top+height,left:left+width]=True
    # Keep actual per-axis resize ratios; integer rounding need not preserve one scale.
    letterbox=np.array([[rgb.width/width,0,-left*rgb.width/width],
                        [0,rgb.height/height,-top*rgb.height/height],[0,0,1]],dtype=np.float64)
    inverse=np.asarray(transform["to_original"],dtype=np.float64)@letterbox
    metadata={"preprocessing_version":config.version,"preprocessing_sha256":config.fingerprint(),
              "original_width":original_width,"original_height":original_height,"rotation_ccw":rotation,
              "size":config.size,"resized_width":width,"resized_height":height,
              "content_box":[left,top,left+width,top+height],"to_original":inverse.tolist()}
    return {"tensor":tensor,"valid_pixel_mask":valid,"transform":metadata}


def box_to_source(box: list[float], metadata: dict) -> list[float]:
    content=metadata["content_box"]
    if (len(box)!=4 or any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in box)
            or not content[0]<=box[0]<box[2]<=content[2] or not content[1]<=box[1]<box[3]<=content[3]):
        raise ValueError("box is outside real letterbox content")
    matrix=metadata["to_original"]
    points=[(matrix[0][0]*x+matrix[0][1]*y+matrix[0][2],matrix[1][0]*x+matrix[1][1]*y+matrix[1][2])
            for x,y in ((box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3]))]
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
