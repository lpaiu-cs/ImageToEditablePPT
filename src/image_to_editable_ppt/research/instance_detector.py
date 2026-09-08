"""R19 native-structure instances; RGB-only inference, explicit training targets."""
import numpy as np
import torch
from torchvision.models import ResNet50_Weights
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.backbone_utils import resnet_fpn_backbone


def new_model(pretrained=False):
    # The helper keeps FrozenBatchNorm identical for training and offline reload.
    backbone=resnet_fpn_backbone(backbone_name='resnet50',
        weights=ResNet50_Weights.IMAGENET1K_V1 if pretrained else None,trainable_layers=5)
    return FasterRCNN(backbone,num_classes=7,min_size=600,max_size=960,
        box_score_thresh=.05,box_nms_thresh=.5,box_detections_per_img=100)


def image_tensor(rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8 RGB required')
    return torch.from_numpy(rgb.copy()).permute(2,0,1).float()/255


def target(objects,size):
    boxes=torch.tensor([o['bbox'] for o in objects],dtype=torch.float32).reshape(-1,4)
    labels=torch.tensor([o['kind'] for o in objects],dtype=torch.int64)
    if len(boxes) and (not torch.isfinite(boxes).all() or not ((boxes[:,2:]>boxes[:,:2]).all()
        and (boxes>=0).all() and (boxes[:,[0,2]]<=size[0]).all() and (boxes[:,[1,3]]<=size[1]).all()
        and ((labels>=1)&(labels<=6)).all())):raise ValueError('Invalid native structure target')
    return dict(boxes=boxes,labels=labels)


def decode(prediction,size,threshold):
    if not 0<=threshold<=1:raise ValueError('Invalid score threshold')
    result=[]
    for i,(box,label,score) in enumerate(zip(prediction['boxes'],prediction['labels'],prediction['scores'],strict=True)):
        values=[float(v) for v in box];kind=int(label);confidence=float(score)
        if not np.isfinite(values+[confidence]).all() or kind not in range(1,7) or not 0<=confidence<=1:raise ValueError('Invalid detection')
        x,y,a,b=values
        if not 0<=x<a<=size[0] or not 0<=y<b<=size[1]:raise ValueError('Detection outside RGB')
        if confidence>=threshold:result.append(dict(id=f'instance:{i}',kind=kind,bbox=values,confidence=confidence))
    return result
