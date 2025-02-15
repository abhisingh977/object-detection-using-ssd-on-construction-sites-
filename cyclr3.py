import time
from typing import List, Any
import wandb
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
from model import SSD300, MultiBoxLoss
from datasets import PascalVOCDataset
from utils import *
import argparse
# Data parameters
data_folder = './'  # folder with data files
keep_difficult = True  # use objects considered difficult to detect?

# Model parameters
# Not too many here since the SSD300 has a very specific structure
n_classes = len(label_map)  # number of different types of objects

torch.cuda.set_device(0)
torch.cuda.current_device()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

import io

import numpy as np



#PATH='C:/Users/Home/Documents/res/res/model.pt'
# Learning
#checkpoint = torch.load(PATH)# path to model checkpoint, None if none
#stream = io.BytesIO(checkpoint.tobytes())
batch_size = 16 # batch size

#iterations = 125  # number of iterations to train
workers = 4  # number of workers for loading data in the DataLoader
  # print training status every __ batches
lr = 1e-3 # learning rate
#decay_lr_at = [60,90] # decay learning rate after these many iterations
#decay_lr_to = 0.1  # decay learning rate to this fraction of the existing learning rate
momentum = 0.9  # momentum
weight_decay = 5e-4  # weight decay
grad_clip = None  # clip if gradients are exploding, which may happen at larger batch sizes (sometimes at 32) - you will recognize it by a sorting error in the MuliBox loss calculation

cudnn.benchmark = True
#iterations = 120000

def main():
    wandb.init()

    # Config is a variable that holds and saves hyperparameters and inputs
    #wandb.watch(model)

    torch.manual_seed(30)
    """
    Training.
    """
    global start_epoch, label_map, epoch, checkpoint, decay_lr_at
    #print(device)
    # Initialize model or load checkpoint
    # if checkpoint is None:
    start_epoch = 79
    model = SSD300(n_classes=n_classes)

    #checkpoint = torch.load(checkpoint)
    # if checkpoint is None:
    #     start_epoch = 0
    #     model = SSD300(n_classes=n_classes)
    #     # Initialize the optimizer, with twice the default learning rate for biases, as in the original Caffe repo
    #     biases: List[Any] = list()
    #     not_biases = list()
    #     for param_name, param in model.named_parameters():
    #         if param.requires_grad:
    #             if param_name.endswith('.bias'):
    #                 biases.append(param)
    #             else:
    #                 not_biases.append(param)
    #     optimizer = torch.optim.SGD(params=[{'params': biases, 'lr': 2 * lr}, {'params': not_biases}],
    #                                 lr=lr, momentum=momentum, weight_decay=weight_decay)
    #
    # else:
    #     checkpoint = torch.load(checkpoint)
    #     start_epoch = checkpoint['epoch'] + 1
    #     print('\nLoaded checkpoint from epoch %d.\n' % start_epoch)
    #     model = checkpoint['model']
    #     optimizer = checkpoint['optimizer']

    # Initialize the optimizer, with twice the default learning rate for biases, as in the original Caffe repo
    biases: List[Any] = list()
    not_biases = list()
    for param_name, param in model.named_parameters():
        if param.requires_grad:
            if param_name.endswith('.bias'):
                biases.append(param)
            else:
                not_biases.append(param)
    optimizer = torch.optim.SGD(params=[{'params': biases, 'lr': 2 * lr}, {'params': not_biases}],
                                lr=lr, momentum=momentum, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CyclicLR(optimizer, base_lr=0.0003,
                                                  max_lr=0.0008, step_size_up=26, step_size_down=26)
    # print(model)
    # else:
    #     checkpoint = torch.load(checkpoint)
    #     start_epoch = checkpoint['epoch'] + 1
    #     print('\nLoaded checkpoint from epoch %d.\n' % start_epoch)
    #     model = checkpoint['model']
    #     optimizer = checkpoint['optimizer']

    # Move to default device
    model = model.to(device)
    checkpoint = torch.load('modelfi.pt')
    model.load_state_dict(checkpoint)
    # checkpoint = torch.load('model_best.pth.tar')
    criterion = MultiBoxLoss(priors_cxcy=model.priors_cxcy).to(device)
    wandb.watch(model, log="all")
    # Custom dataloaders
    train_dataset = PascalVOCDataset(data_folder,
                                     split='train',
                                     keep_difficult=keep_difficult)
   # print(train_dataset)
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True,
                                               collate_fn=train_dataset.collate_fn, num_workers=workers,
                                               pin_memory=True)  # note that we're passing the collate function here


    test_dataset = PascalVOCDataset(data_folder,split='test', keep_difficult=keep_difficult)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=True,
                                              collate_fn=test_dataset.collate_fn, num_workers=workers, pin_memory=True)
    #print(next(iter(test_loader)))
#    print(train_loader)
#    a=next(iter(train_loader))
#    print(a)
    # Calculate total number of epochs to train and the epochs to decay learning rate at (i.e. convert iterations to epochs)
    # To convert iterations to epochs, divide iterations by the number of iterations per epoch
    # The paper trains for 120,000 iterations with a batch size of 32, decays after 80,000 and 100,000 iterations
   # epochs = iterations // (len(train_dataset) // 8)
    #print(epochs)
    #decay_lr_at = [it // (len(train_dataset) // 32) for it in decay_lr_at]

    epochs = 100
    # Epochs
    for epoch in range(start_epoch, epochs):
        #
        # # Decay learning rate at particular epochs
        # if epoch in decay_lr_at:
        #     adjust_learning_rate(optimizer, decay_lr_to)

        # One epoch's training
        train(train_loader=train_loader,
              model=model,
              scheduler=scheduler,
              criterion=criterion,
              optimizer=optimizer,
              epoch=epoch)
        test(test_loader=test_loader,
              model=model,
              criterion=criterion,
              #optimizer=optimizer,
              epoch=epoch)

        # Save checkpoint
        #save_checkpoint(epoch, model, optimizer)


def train(train_loader,scheduler, model, criterion, optimizer, epoch):
    """
    One epoch's training.

    :param train_loader: DataLoader for training data
    :param model: model
    :param criterion: MultiBox loss
    :param optimizer: optimizer
    :param epoch: epoch number
    """
    model.train()  # training mode enables dropout

   # batch_time = AverageMeter()  # forward prop. + back prop. time
    data_time = AverageMeter()  # data loading time
    losses = AverageMeter()  # loss

    start = time.time()

    # Batches
    tott_loss=0
    counter=0
    for i, (images, boxes, labels, _) in enumerate(train_loader):
        #print(i)
        #print(i)
        # counter+=1
        # print(counter)
#        print(boxes)

        data_time.update(time.time() - start)

        # Move to default device
        images = images.to(device)  # (batch_size (N), 3, 300, 300)
        boxes = [b.to(device) for b in boxes]
        labels = [l.to(device) for l in labels]

        # Forward prop.
        predicted_locs, predicted_scores = model(images)  # (N, 8732, 4), (N, 8732, n_classes)

        # Loss
        loss = criterion(predicted_locs, predicted_scores, boxes, labels)  # scalar

        # Backward prop.
        optimizer.zero_grad()
        loss.backward()

        # Clip gradients, if necessary
        if grad_clip is not None:
            clip_gradient(optimizer, grad_clip)

        # Update model
        optimizer.step()
        #print(loss.item())
        losses.update(loss.item(), images.size(0))
        #batch_time.update(time.time() - start)
        tott_loss+=loss
        start = time.time()
        scheduler.step()

        # Print status
        if i  ==  len(train_loader)-1:
            print('Epoch: [{0}]\t'
                  'Data Time {data_time.val:.3f} ({data_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(epoch,
                                                                 # batch_time=batch_time,
                                                                  data_time=data_time, loss=losses))
            wandb.log({"Epoch":epoch, "Train Loss": (tott_loss / len(train_loader))})
        #
        # if i == len(train_loader)-1 == 0:
        #     print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
        #         epoch, i * len(labels), len(train_loader.dataset),
        #         100. * i / len(train_loader), losses))


    del predicted_locs, predicted_scores, images, boxes, labels  # free some memory since their histories may be stored



def test(test_loader, model, criterion, epoch):
    """
    One epoch's training.

    :param train_loader: DataLoader for training data
    :param model: model
    :param criterion: MultiBox loss
    :param optimizer: optimizer
    :param epoch: epoch number
    """
    model.eval()   # training mode enables dropout

    with torch.no_grad():
        #batch_time = AverageMeter()  # forward prop. time
        data_time = AverageMeter()  # data loading time
        losses_test = AverageMeter()  # loss
        tot_loss=0
        start = time.time()

        # Batches
        for i, (images, boxes, labels, _) in enumerate(test_loader):
    #        print(i)
    #        print(boxes)
            data_time.update(time.time() - start)

            # Move to default device
            images = images.to(device)  # (batch_size (N), 3, 300, 300)
            boxes = [b.to(device) for b in boxes]
            labels = [l.to(device) for l in labels]

            # Forward prop.
            predicted_locs, predicted_scores = model(images)  # (N, 8732, 4), (N, 8732, n_classes)

            # Loss
            loss = criterion(predicted_locs, predicted_scores, boxes, labels)  # scalar

            # Backward prop.
            # optimizer.zero_grad()
            # loss.backward()

            # Clip gradients, if necessary
            # if grad_clip is not None:
            #     clip_gradient(optimizer, grad_clip)
            #
            # # Update model
            # optimizer.step()

            #loss.item()
            losses_test.update(loss.item(), images.size(0))
            #batch_time.update(time.time() - start)

            start = time.time()

            tot_loss+=loss
            #print(tot_loss)

            # Print status
            if i  == len(test_loader)-1:
                print('Epoch: [{0}]\t'
                      'Data Time {data_time.val:.3f} ({data_time.avg:.3f})\t'
                      'Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(epoch,
                                                                      #batch_time=batch_time,
                                                                      data_time=data_time, loss=losses_test))

                wandb.log({"Epoch":(epoch),
                   "Test Loss":(tot_loss/len(test_loader))})
        del predicted_locs, predicted_scores, images, boxes, labels  # free some memory since their histories may be stored

        torch.save(model.state_dict(), os.path.join(wandb.run.dir, 'modelfi.pt'))



















if __name__ == '__main__':
    main()
