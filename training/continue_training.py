import torch
from utils.logger import Logger
from utils.datasets import DetectionDataset
from torch.utils.data import DataLoader, SubsetRandomSampler
import albumentations
from utils.loss import Loss, LossCounter
from utils.utils import from_yolo_target, xywh2xyxy, compute_iou
import os
import numpy as np


PATH_TO_TRAIN_DIR = 'log/detection/20.03.25_19-34'
load = torch.load(os.path.join(PATH_TO_TRAIN_DIR, 'checkpoint.pt'))

logger = Logger('logger', task='detection', session_id=PATH_TO_TRAIN_DIR.split('/')[2])

# Declaring hyperparameters
n_epoch = 120
batch_size = 11
image_size = (320, 320)
grid_size = 5
num_bboxes = 2
val_split = 0.03

# Initiating detection_model and device (cuda/cpu)
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
model = torch.load(os.path.join(PATH_TO_TRAIN_DIR, 'model.pt'))
model.load_state_dict(load['model_state_dict'])

# Initiating optimizer and scheduler for training steps
# optimizer = torch.optimizer.SGD(detection_model.parameters(), lr=0.0001, momentum=0.9, weight_decay=0.0005)
optim = torch.optim.Adam(model.parameters())
optim.load_state_dict(load['optim_state_dict'])

scheduler = torch.optim.lr_scheduler.MultiStepLR(optim, [10])
scheduler.load_state_dict(load['scheduler_state_dict'])

# Declaring augmentations for images and bboxes
train_transforms = albumentations.Compose([
    albumentations.RandomSizedBBoxSafeCrop(height=image_size[0], width=image_size[1], always_apply=True),
    albumentations.HorizontalFlip(p=0.5),
    albumentations.Rotate(15, p=0.5),

], bbox_params=albumentations.BboxParams(format='pascal_voc', label_fields=['labels']))

# Decalring dataset and creating dataloader for train and validation phase
dataset = DetectionDataset(transform=train_transforms, grid_size=grid_size, num_bboxes=num_bboxes)

dataset_len = len(dataset)
val_len = int(np.floor(val_split * dataset_len))
val_idxs = np.random.choice(list(range(dataset_len)), val_len)
train_idxs = list(set(list(range(dataset_len))) - set(val_idxs))

train_sampler = SubsetRandomSampler(train_idxs)
val_sampler = SubsetRandomSampler(val_idxs)

train_dataloader = DataLoader(dataset, shuffle=False, batch_size=batch_size, sampler=train_sampler)
val_dataloader = DataLoader(dataset, shuffle=False, batch_size=batch_size, sampler=val_sampler)

# Declaring loss function
loss = Loss(grid_size=grid_size, num_bboxes=num_bboxes)


# Training loop
for epoch in range(int(load['epoch']), n_epoch):
    batch_train_loss = LossCounter()
    batch_val_loss = LossCounter()
    batch_val_metrics = 0

    for phase in ['train', 'val']:

        if phase == 'train':
            dataloader = train_dataloader
            model.train()
        else:
            dataloader = val_dataloader
            model.eval()

        for i, (image, target, face_rect) in enumerate(dataloader):
            image = image.to(device)
            target = target.to(device)

            optim.zero_grad()
            with torch.set_grad_enabled(phase == 'train'):
                output = model(image)
                loss_value, logger_loss = loss(output, target)

                if phase == 'train':
                    # Parameters updating
                    loss_value.backward()
                    optim.step()
                    scheduler.step(epoch)

                    batch_train_loss += logger_loss
                else:
                    face_rect.to(device)
                    listed_output = torch.tensor(
                        from_yolo_target(output, image_w=image_size[0], grid_size=grid_size, num_bboxes=num_bboxes))
                    preds = torch.empty((listed_output.size(0), 5))
                    idxs = torch.argmax(listed_output[:, :, 4], dim=1)
                    for batch in range(listed_output.size(0)):
                        preds[batch] = listed_output[batch, idxs[batch], ...]

                    batch_val_loss += logger_loss
                    batch_val_metrics += compute_iou(face_rect,
                                                     torch.tensor(xywh2xyxy(preds[:, :4]), dtype=torch.float), num_bboxes=2).mean().item()
    epoch_train_loss = LossCounter({key: value / len(train_dataloader) for key, value in batch_train_loss.items()})
    epoch_val_loss = LossCounter({key: value / len(val_dataloader) for key, value in batch_val_loss.items()})
    epoch_val_metrics = batch_val_metrics / len(val_dataloader)

    logger.epoch_info(epoch=epoch, train_loss=epoch_train_loss, val_loss=epoch_val_loss, val_metrics=epoch_val_metrics)

    if epoch % 5 == 0:
        # Checkpoint. Saving detection_model, optimizer, scheduler and train info
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optim_state_dict': optim.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
            'train_loss': batch_train_loss['Total loss q']
        }, os.path.join(PATH_TO_TRAIN_DIR, 'checkpoint.pt'))
        logger.info('!Checkpoint created!')
