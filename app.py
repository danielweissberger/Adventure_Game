#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from os import environ as env
from sys import argv

import bottle
from bottle import default_app, request, route, response, get

bottle.debug(True)


from bottle import route, run, template, static_file, request
import random
import json
import pymysql
from random import randint


connection = pymysql.connect(host = "sql11.freesqldatabase.com",
                             user = "sql11157875",
                             password = "dwh3JthIai",
                             db="sql11157875",
                             charset="utf8",
                             cursorclass = pymysql.cursors.DictCursor)


def getRemainingQs(questionsUsed, questions):
    questionArray = list(range(int(questions["max"]) + 1))
    questionArray.pop(0)
    questionsUsed = questionsUsed.split(',')
    remainingQs = []
    for question in questionArray:
        if str(question) not in questionsUsed:
            remainingQs.append(question)
    return remainingQs

def getNextQuestions(remainingQs,options):
    qList = []
    remaining = len(remainingQs)

    for q in range(0,remaining):
        rand = randint(0,len(remainingQs)-1)
        qList.append(remainingQs[rand])
        remainingQs.pop(rand)

    if len(qList)<len(options):
        diff = len(options)-len(qList)
        rand = randint(0,1)
        if rand == 0:
            for i in range(0,diff):
                qList = [qList[randint(0,len(qList)-1)]]+qList
        else:
            for i in range(0,diff):
                qList = qList+[qList[randint(0,len(qList)-1)]]

    else:
        qList = qList[0:len(options)]

    return qList


def getQuestionAndOptions(cursor, sequence_num,current_adv_id):
    sql = "SELECT QS.id as id, question, image_src FROM questions as QS LEFT JOIN images as IM ON QS.image_id =IM.id WHERE sequence ={} AND QS.adventure_id = {}".format(
        sequence_num, current_adv_id)
    cursor.execute(sql)
    question_data = cursor.fetchone()

    question_id = question_data["id"]
    sql = "SELECT opt.id as id, option_text,life_loss,coin_loss FROM options as opt LEFT JOIN q_and_o as qo ON opt.id = qo.o_id WHERE q_id = {}".format(
        question_id)
    cursor.execute(sql)
    option_data = cursor.fetchall()


    return (question_data,option_data)



@route("/", method="GET")
def index():
    return template("adventure.html")

@route("/start", method="POST")
def start():
    username = request.POST.get("user")
    current_adv_id = request.POST.get("adventure_id")

    with connection.cursor() as cursor:

        sql = "SELECT id, user_name FROM users"
        cursor.execute(sql)
        user_data = cursor.fetchall()

        #If the user is new, add him to the table, else fetch his/her id

        if (username not in [user["user_name"] for user in user_data]):
            sql = "INSERT INTO users (user_name) VALUES ('{}')".format(username)
            cursor.execute(sql)
            cursor.execute("SELECT LAST_INSERT_ID()")
            id = cursor.fetchone()["LAST_INSERT_ID()"]
            sql = "INSERT INTO games (user_id,adventure_id,progress,coins_remaining,life_remaining) VALUES ({},{},'1',40,100)".format(id,current_adv_id)
            cursor.execute(sql)
            connection.commit()

        else:
            for user in user_data:
                if user["user_name"]==username:
                    id = user["id"]

        #Fetch users progress
        sql = "SELECT * FROM games WHERE user_id = {} AND adventure_id = {}".format(id,current_adv_id)
        cursor.execute(sql)
        user_game = cursor.fetchone()

        #User exists already but has no running games then add a new game and return the game data
        if user_game == None:
            sql = "INSERT INTO games (user_id,adventure_id,progress,coins_remaining,life_remaining) VALUES ({},{},'1',40,100)".format(id,current_adv_id)
            cursor.execute(sql)
            connection.commit()
            sql = "SELECT * FROM games WHERE user_id = {} AND adventure_id = {}".format(id,current_adv_id)
            cursor.execute(sql)
            user_game = cursor.fetchone()

        #Get the total number of questions for this game
        sql = "SELECT max(sequence) AS max FROM questions WHERE adventure_id = {}".format(current_adv_id)
        cursor.execute(sql)
        questions = cursor.fetchone()

        #Get the remaining questions that the user has not seen
        remainingQs = getRemainingQs(user_game["progress"],questions)
        progress = user_game["progress"].split(',')
        sequence_num = progress[len(progress)-1]

        #Get questions and options
        question_and_option_data = getQuestionAndOptions(cursor, sequence_num, current_adv_id)

        #Retrieve a randomized array of 4 possible new questions if there are more questions (skip if user is on last step)
        # grap 1 question for each option (duplicates are possible if less than 4 questions remain when restarting game)
        if len(remainingQs) > 0:
            options = getNextQuestions(remainingQs,question_and_option_data[1])

            #Add the next question options to the option data retrieved above
            for option in question_and_option_data[1]:
                option["next_step"]= options.pop(0)


    return json.dumps({"user": id,
                       "questions":questions,
                       "adventure": current_adv_id,
                       "text": question_and_option_data[0]["question"],
                       "image": question_and_option_data[0]["image_src"],
                       "options": question_and_option_data[1],
                       "coins_remaining":user_game["coins_remaining"],
                       "life_remaining":user_game["life_remaining"]
                       })


@route("/story", method="POST")
def story():
    alert = ""
    user_id = request.POST.get("user")
    questions = json.loads(request.POST.get("questions"))
    current_adv_id = request.POST.get("adventure")
    sequence_num = request.POST.get("next")
    option_id = int(request.POST.get("option_id"))
    try:
        with connection.cursor() as cursor:
            #Get coin and life to deduct from the option id sent in from the POST request
            sql = "SElECT coin_loss, life_loss FROM options WHERE id = {}".format(option_id)
            cursor.execute(sql)
            coin_life_data = cursor.fetchone()
            coin_loss = coin_life_data["coin_loss"]
            life_loss = coin_life_data["life_loss"]

            sql = "SELECT * FROM games WHERE user_id = {}".format(user_id)
            cursor.execute(sql)
            game_data = cursor.fetchone()
            coins_remaining = game_data["coins_remaining"]-coin_loss
            life_remaining = max(game_data["life_remaining"]-life_loss,0)
            #grab users progress, get the length of the progress, and udpate the progress
            progress = game_data["progress"]
            progress_length = len(progress.split(","))
            progress += "," + str(sequence_num)

            if life_remaining >0 and progress_length <8 and coins_remaining >=0:
                sql = "UPDATE games SET progress = '{}',coins_remaining = {},life_remaining={} WHERE user_id = {}".format(progress,coins_remaining,life_remaining,user_id)
                cursor.execute(sql)
                connection.commit()

                #Get questions and options
                question_and_option_data = getQuestionAndOptions(cursor,sequence_num,current_adv_id)
                question = question_and_option_data[0]["question"]
                image = question_and_option_data[0]["image_src"]
                option_data = question_and_option_data[1]

                remainingQs = getRemainingQs(progress, questions)

                if len(remainingQs)>0:
                    options = getNextQuestions(remainingQs, option_data)

                    for option in option_data:
                        option["next_step"] = options.pop(0)
            else:
                #Check if life below 0 (Game over), GAME IS WON, Or the player has insufficient funds
                if life_remaining <=0:
                    image = "gameover.jpg"
                    question = "You lost this one"
                    option_data = []
                    sql = "DELETE FROM games WHERE user_id = {}".format(user_id)
                    cursor.execute(sql)
                    connection.commit()
                    if coins_remaining <0:
                        coins_remaining = coins_remaining + coin_loss
                elif coins_remaining <0:
                    image = ""
                    question = ""
                    option_data = []
                    coins_remaining = coins_remaining + coin_loss
                    alert = "coin_problem"
                else:
                    image = "victory.png"
                    question = "Great job you won this one"
                    option_data = []
                    sql = "DELETE FROM games WHERE user_id = {}".format(user_id)
                    cursor.execute(sql)
                    connection.commit()


        return json.dumps({"user": user_id,
                           "adventure": current_adv_id,
                           "text": question,
                           "image": image,
                           "options": option_data,
                           "coins_remaining":coins_remaining,
                           "life_remaining":life_remaining,
                           "alert":alert
                           })
    except:
        return json.dumps({"user": user_id,
                           "adventure": current_adv_id,
                           "text": question,
                           "image": image,
                           "options": option_data,
                           "coins_remaining":coins_remaining,
                           "life_remaining":life_remaining,
                           "alert":alert
                           })



@route('/js/<filename:re:.*\.js$>', method='GET')
def javascripts(filename):
    return static_file(filename, root='js')


@route('/css/<filename:re:.*\.css>', method='GET')
def stylesheets(filename):
    return static_file(filename, root='css')


@route('/images/<filename:re:.*\.(jpg|png|gif|ico)>', method='GET')
def images(filename):
    return static_file(filename, root='images')


def main():
    #run(host='0.0.0.0', port=argv[1]) # - RUN ON HEROKU, COMMENT TO RUN LOCALLY
    run(host='localhost',port=7000)  #-- UNCOMMENT THIS TO RUN LOCALLY

if __name__ == '__main__':
    main()