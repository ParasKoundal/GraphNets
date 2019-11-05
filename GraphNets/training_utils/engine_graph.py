# Python standard imports
from sys import stdout
from math import floor
from time import strftime, localtime

# PyTorch imports
import torch
import torch.nn.functional as F
from torch.optim import Adam

from training_utils.engine import Engine
from training_utils.logger import CSVData


class EngineGraph(Engine):

    def __init__(self, model, config):
        super().__init__(model, config)
        self.criterion=F.nll_loss
        self.optimizer=Adam(self.model_accs.parameters(), lr=config.lr)
        
        self.keys = ['iteration', 'epoch', 'loss', 'acc']

    def forward(self, data, mode="train"):
        """Overrides the forward abstract method in Engine.py.
        
        Args:
        mode -- One of 'train', 'validation' 
        """

        # Set the correct grad_mode given the mode
        if mode == "train":
            self.model.train()
        elif mode in ["validation"]:
            self.model.eval()

        return self.model(data)

    def train(self):
        """Overrides the train method in Engine.py.
        
        Args: None
        """
        
        epochs          = self.config.epochs
        report_interval = self.config.report_interval
        valid_interval  = self.config.valid_interval
        num_val_batches = self.config.num_val_batches

        # Initialize counters
        epoch=0.
        iteration=0

        # Parameter to upadte when saving the best model
        best_loss=1000000.

        val_iter = iter(self.val_loader)
        
        # Global training loop for multiple epochs
        while (floor(epoch) < epochs):

            print('Epoch {:2.0f}'.format(epoch),
                  'Starting @', strftime("%Y-%m-%d %H:%M:%S", localtime()))

            # Local training loop for a single epoch
            for data in self.train_loader:
                data = data.to(self.device)

                # Update the epoch and iteration
                epoch+=1. / len(self.train_loader)
                iteration += 1
                
                # Do a forward pass using data = self.data
                res=self.forward(data, mode="train")

                # Do a backward pass using loss = self.loss
                loss = self.backward(res, data.y)

                acc = res.argmax(1).eq(data.y).sum().item()/data.y.shape[0]
                
                # Record the metrics for the mini-batch in the log
                self.train_log.record(self.keys, [iteration, epoch, loss, acc])
                self.train_log.write()

                # Print the metrics at given intervals
                if iteration % report_interval == 0:
                    print("... Iteration %d ... Epoch %1.2f ... Loss %1.3f ... Acc %1.3f"
                          % (iteration, epoch, loss, acc))

                # Run validation on given intervals
                if iteration % valid_interval == 0:
                    with torch.no_grad():
                        val_loss=0.
                        val_acc=0.

                        for val_batch in range(num_val_batches):

                            try:
                                data=next(val_iter)
                            except StopIteration:
                                val_iter=iter(self.val_loader)
                                data=next(val_iter)
                            data = data.to(self.device)

                            # Extract the event data from the input data tuple
                            res=self.forward(data, mode="validation")
                            acc = res.argmax(1).eq(data.y).sum().item()/data.y.shape[0]

                            val_loss+=self.criterion(res, data.y)
                            val_acc+=acc

                        val_loss /= num_val_batches
                        val_acc /= num_val_batches

                        # Record the validation stats to the csv
                        self.val_log.record(self.keys, [iteration, epoch, loss, acc])
                        self.val_log.write()

                        # Save the best model
                        if val_loss < best_loss:
                            self.save_state(mode="best")
                            best_loss = val_loss

                        # Save the latest model
                        self.save_state(mode="latest")
                    

        self.val_log.close()
        self.train_log.close()

    def validate(self, subset):
        """Overrides the validate method in Engine.py.
        
        Args:
        subset          -- One of 'train', 'validation', 'test' to select the subset to perform validation on
        """
        # Print start message
        if subset == "train":
            message="Validating model on the train set"
        elif subset == "validation":
            message="Validating model on the validation set"
        elif subset == "test":
            message="Validating model on the test set"
        else:
            print("validate() : arg subset has to be one of train, validation, test")
            return None

        print(message)
        
        # Setup the CSV file for logging the output, path to save the actual and reconstructed events, dataloader iterator
        if subset == "train":
            self.log=CSVData(self.dirpath + "train_validation_log.csv")
            np_event_path=self.dirpath + "/train_valid_iteration_"
            data_iter=self.train_loader
        elif subset == "validation":
            self.log=CSVData(self.dirpath + "valid_validation_log.csv")
            np_event_path=self.dirpath + "/val_valid_iteration_"
            data_iter=self.val_loader
        else:
            self.log=CSVData(self.dirpath + "test_validation_log.csv")
            np_event_path=self.dirpath + "/test_validation_iteration_"
            data_iter=self.test_loader

        save_arr_dict={"events": [], "labels": [], "energies": []}
        
        with torch.no_grad():
            for iteration, data in enumerate(data_iter):
                data = data.to(self.device)

                stdout.write("Iteration : {}, Progress {} \n".format(iteration, iteration/len(data_iter)))
                res=self.forward(data, mode="validation")
                acc = res.argmax(1).eq(data.y).sum().item()/data.y.shape[0]
                loss = self.criterion(res, data.y)

                # Log/Report
                self.log.record(["Iteration", "loss", "acc"], [iteration, loss, acc])
                self.log.write()
