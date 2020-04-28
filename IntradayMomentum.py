import datetime
import logging
import threading
import time
from csv import DictWriter
from threading import Timer
import pandas as pd
import os
from ibapi.commission_report import CommissionReport
from ibapi.common import TickerId, TickAttrib, BarData
from ibapi.client import EClient, OrderId  ##Outgoing messages
from ibapi.execution import Execution
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper, TickType  ##Incoming messages
from ibapi.contract import Contract, ContractDetails
from datetime import date
import schedule
import asyncio

class IntradayMomentum(EWrapper,EClient):

    def __init__(self, isMorning, quantity,first_n_stock = 5):
        EClient.__init__(self,self)

        self.nextValidOrderId = None
        self.isMorning = isMorning
        self.date = datetime.date.today().strftime("%d%m%Y")
        self.started = False
        self.globalCancelOnly = False
        self.first_n_stock = first_n_stock
        self.quantity = quantity

        self.scanner_path = "/Users/alperoner/PycharmProjects/PMP/IntradayMomentum/Scanner/{}_scanner.csv".format(self.date)

        self.cr_path = "/Users/alperoner/PycharmProjects/PMP/IntraDayMomentum/Executions/{}_commission_report.csv".format(self.date)
        self.ee_path = "/Users/alperoner/PycharmProjects/PMP/IntraDayMomentum/Executions/{}_evening_executions.csv".format(self.date)
        self.me_path = "/Users/alperoner/PycharmProjects/PMP/IntraDayMomentum/Executions/{}_morning_executions.csv".format(self.date)
        self.sh_path =  "/Users/alperoner/PycharmProjects/PMP/IntraDayMomentum/strategy_history.csv"

        self.cr_columns = ["exec_id","realized_pnl"]
        self.ee_columns = ["date","exec_id", "ticker","sec_type","quantity_sold","avg_price_sold"]
        self.me_columns = ["date", "exec_id", "ticker", "sec_type", "quantity_bought", "avg_price_bought"]
        self.sh_columns = ["exec_id","realized_pnl",
                          "date","exec_id", "ticker",
                          "sec_type","quantity_sold",
                          "avg_price_sold","quantity_bought",
                          "avg_price_bought"]

        if os.path.isfile(self.scanner_path):
            self.scanner = pd.read_csv(self.scanner_path)
        else:
             raise("Scanner file does not exist")

        ## Should check if these files exist
        self.commission_report = self.check_file(self.cr_path,self.cr_columns)
        self.evening_executions = self.check_file(self.ee_path,self.ee_columns)
        self.morning_executions = self.check_file(self.me_path,self.me_columns)
        self.strategy_history = self.check_file(self.sh_path, self.sh_columns)

    def check_file(self, path, columns):

        if os.path.isfile(path):
            print ("File exist at path: {}".format(path))
            data = pd.read_csv(path)
        else:
            data = pd.DataFrame(columns=[columns]).to_csv(path, index=False)

        return data

    def append_dict_as_row(self,file_name, dict_of_elem, field_names):
        # Open file in append mode
        with open(file_name, 'a+', newline='') as write_obj:
            # Create a writer object from csv module
            dict_writer = DictWriter(write_obj, fieldnames=field_names)
            # Add dictionary as wor in the csv
            dict_writer.writerow(dict_of_elem)


    def nextOrderId(self):
        oid = self.nextValidOrderId
        self.nextValidOrderId += 1
        return oid

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)

        logging.debug("setting nextValidOrderId: %d", orderId)
        self.nextValidOrderId = orderId
        print("NextValidId:", orderId)
    # ! [nextvalidid]

        # we can start now
        self.start()

    def start(self):
        if self.started:
            return

        self.started = True

        ##Questionable
        if self.globalCancelOnly:
            print("Executing GlobalCancel only")
            self.reqGlobalCancel()
        else:
            self.routine()




    def orderStatus(self, orderId:OrderId , status:str, filled:float,
                    remaining:float, avgFillPrice:float, permId:int,
                    parentId:int, lastFillPrice:float, clientId:int,
                    whyHeld:str, mktCapPrice: float):
        print("")
#       print("OrderStatus. Id: ", orderId, ", Status: ", status,
#              " Filled: ", filled, " Remaining: ", remaining,
#              " Last Fill Price: ", lastFillPrice, "Avg Fill Price: ", avgFillPrice)

    def openOrder(self, orderId:OrderId, contract:Contract, order:Order,
                  orderState:OrderState):
        print("OpenOrder. Id: ", orderId, contract.symbol, contract.secType,"@", contract.exchange,":", order.action,
              order.orderType,order.totalQuantity, orderState.status)

    def execDetails(self, reqId:int, contract:Contract, execution:Execution):
        print("ExecDetails. ", reqId, contract.symbol, contract.secType, contract.currency, execution.execId,
              execution.orderId, execution.shares,execution.avgPrice)


        if self.isMorning:
            row = {"date": [self.today], "exec_id":[execution.execId],
                   "ticker": [contract.symbol],"sec_type": [contract.secType],
                   "quantity_bought": [execution.cumQty], "avg_price_bought": [execution.avgPrice]}

            self.append_dict_as_row(self.me_path,row,self.me_columns)

        else:
            row = {"date": [self.today], "exec_id":[execution.execId],
                   "ticker": [contract.symbol], "sec_type": [contract.secType],
                   "quantity_sold": [execution.cumQty], "avg_price_sold": [execution.avgPrice]}

            self.append_dict_as_row(self.ee_path, row, self.ee_columns)


    def execDetailsEnd(self, reqId:int):
        print("Execution ended")

    def commissionReport(self, commissionReport:CommissionReport):
        super().commissionReport(commissionReport)
        print("CommissionReport.", commissionReport)

        if not self.isMorning:
            row = {"exec_id": [commissionReport.execId], "realized_pnl": [commissionReport.realizedPNL]}
            self.append_dict_as_row(self.cr_path, row, self.cr_columns)


    def error(self, reqId:TickerId, errorCode:int, errorString:str):
        print("Error: ", reqId, " ", errorCode," ", errorString)

    def get_contract(self,ticker: str):
        contract = Contract()
        contract.symbol = ticker
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    def get_order(self, quantity:int, action: str):
        order = Order()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = "MKT"
        return order

    def contract_list(self, tickers):
        return [self.get_contract(ticker) for ticker in tickers]

    def end_day(self):

        me = pd.read_csv(self.me_path)
        ee = pd.read_csv(self.ee_path)
        cr = pd.read_csv(self.cr_path)


        if len(me) == 0 or me is None:
            raise("Morning Executions did not establish")
        if len(ee) == 0 or ee is None:
            raise("Evening Executions did not establish")

        data = me.merge(ee, how= "inner")
        data = data.merge(cr, how="inner")

        data["return"] = 100 * data.realized_pnl / (data.AvgPrice_Bought*data.quantity_bought)

        data.to_csv(self.sh_path, mode='a', header=False)

    ##Call stop after 3 seconds to disconnect program
    def stop(self):
        self.done = True
        self.disconnect()

    def execute_orders(self,contracts, order):
        for contract in contracts:
            self.placeOrder(self.nextOrderId(),contract, order)

    def tickPrice(self, reqId:TickerId , tickType:TickType, price:float,
                  attrib:TickAttrib):
        print("TickerId: ", reqId, "Price: ", price)

    def tickSnapshotEnd(self, reqId:int):
        print("Snapshot ended")




    def getPrices(self, tickers):
        print("")
        ##Use daily prices in the folder to receive price and stock quantity data

    def routine(self):

        if self.isMorning:
            end_index = self.first_n_stock-1
            stocks = self.scanner.loc[0:end_index]
            tickers = stocks.ticker.values


            order = self.get_order(quantity=self.quantity, action="BUY")

        else:
            stocks = pd.read_csv(self.me_path)
            tickers = stocks.ticker.values
            order = self.get_order(quantity=self.quantity, action="SELL")

        self.execute_orders(self.contract_list(tickers=tickers),order)
        print("Routine completed")


def morning():
    
    strategy = IntradayMomentum(isMorning= True,quantity=5)
    strategy.connect("127.0.0.1", 7497, 1)
    Timer(3, strategy.stop).start()
    strategy.run()

def evening():

    strategy = IntradayMomentum(isMorning= False,quantity=5)
    strategy.connect("127.0.0.1", 7497, 1)
    Timer(3, strategy.end_day).start()
    Timer(5, strategy.stop).start()
    strategy.run()

morning()