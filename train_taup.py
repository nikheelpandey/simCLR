
import os
import time
import torch 
import numpy as np
from tqdm import tqdm 
import torch.optim as optim
from datetime import datetime 
from knn_monitor import knn_monitor
from tensorboardX import SummaryWriter
from torch.optim.lr_scheduler import ExponentialLR


from logger import Logger
from loss import ContrastiveLoss
from torchvision.models import resnet18
from dataset_loader import  gpu_transformer
from model import ContrastiveModel, get_backbone
from dataset_loader import get_train_mem_test_dataloaders




if torch.cuda.is_available():
    dtype = torch.cuda.FloatTensor
    device = torch.device("cuda")
    # torch.cuda.set_device(device_id)
    print('GPU')
else:
    dtype = torch.FloatTensor
    device = torch.device("cpu")



uid = 'SimCLR'
dataset_name = 'cifar10'
data_dir = 'dataset'
ckpt_dir = "./ckpt/"+str(datetime.now().strftime('%m%d%H%M%S'))
log_dir = "runs/"+str(datetime.now().strftime('%m%d%H%M%S'))

#create dataset folder 
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
# Setup asset directories
if not os.path.exists(ckpt_dir):
    os.makedirs(ckpt_dir)

if not os.path.exists(log_dir):
    os.makedirs(log_dir)
    
logger = Logger(log_dir=log_dir, tensorboard=True, matplotlib=True)


backbone= get_backbone(resnet18(pretrained=False))
model = ContrastiveModel(backbone).to(device)
loss_func  = ContrastiveLoss().to(device)


features = 128
batch_size = batch = 2048
epochs = 25
lr = 1e-4
device_id = 0
wt_decay  = 0.90
image_size = (32,32)


optimizer = optim.Adam(model.parameters(), 
            lr=lr,
            weight_decay=wt_decay) 
scheduler = ExponentialLR(optimizer, gamma= wt_decay)

min_loss = np.inf #ironic
accuracy = 0



train_loader, memory_loader, test_loader = get_train_mem_test_dataloaders(
                dataset="cifar10", 
                data_dir="./dataset",
                batch_size=batch_size,
                num_workers=4, 
                download=True )

train_transform , test_transform = gpu_transformer(image_size)



global_progress = tqdm(range(0, epochs), desc=f'Training')
data_dict = {"loss": 100}
for epoch in global_progress:
    model.train()   
    local_progress = tqdm(train_loader, desc=f'Epoch {epoch}/{epochs}')
    
    for idx, (image, label) in enumerate(local_progress):
        image = image.to(device)
        aug_image = train_transform(image)
        model.zero_grad()
        z = model.forward(image.to(device, non_blocking=True))
        z_= model.forward(aug_image.to(device, non_blocking=True))
        loss = loss_func(z,z_) 
        data_dict['loss'] = loss.item() 
        loss.backward()
        optimizer.step()
        scheduler.step()
        data_dict.update({'lr': scheduler.get_last_lr()[0]})
        local_progress.set_postfix(data_dict)
        logger.update_scalers(data_dict)
    
    current_loss = data_dict['loss']
    accuracy = knn_monitor(model.backbone, memory_loader, test_loader, 'cpu', hide_progress=True) 
    data_dict['accuracy'] = accuracy
    epoch_dict = {'epoch':epoch, 'accuracy':accuracy}
    global_progress.set_postfix(data_dict)
    logger.update_scalers(data_dict)
    
    model_path = os.path.join(ckpt_dir, f"{uid}_{datetime.now().strftime('%m%d%H%M%S')}.pth")

    if min_loss > current_loss:
        min_loss = current_loss
        
        torch.save({
        'epoch':epoch+1,
        'state_dict': model.state_dict() }, model_path)
        print(f'Model saved at: {model_path}')