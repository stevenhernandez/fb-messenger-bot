import os
import sys
import json
import boto3
from pymessenger.bot import Bot

import requests
from flask import Flask, request

app = Flask(__name__)
bot = Bot("EAAD0GgditLsBAEOaCmRSpSHZCcer6BsGNizdj0KPiodpsNWK1a76s9GBDfiUk5uPVWKqOdEM3WnAeJSGQs68tYA4obE56pRCr7GvQr1B7E6W6giAxEIQxZBA7ZA0HVkrtoj3NiOHT1JZCqvDzRcfFVfk87MbVWpowF0H1mEOogZDZD")#Bot(os.environ["PAGE_ACCESS_TOKEN"])

chocolateDict = {
    "Kit Kat",
    "Rollo",
    "Twix"
}

fruityDict = {
    "Starburst",
    "Smarties",
    "Blow Pops"
}

candyCategory = {
    "chocolate": chocolateDict,
    "fruity": fruityDict
}

ongoingReviewActions = {
    "Complete Review":"Complete Review"
}

newReviewActions = {
    "Complete Review":"Complete Review",
    "Continue Review":"Continue Review"
}

cdv = [
    ("Are you still craving candy?", {"Yes", "No"}),
    ("Will you vote for the CandyCrew to win the Hackathon?", { "Yes", "Definitely!"})
]

sdb = boto3.client('sdb')

domainName = 'steven.hernandez'

@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


@app.route('/', methods=['POST'])
def webhook():

    # endpoint for processing incoming messaging events

    data = request.get_json()
    log(data)  # you may not want to log every incoming message in production, but it's good for testing

    if data["object"] == "page":

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:
                sender_id = messaging_event["sender"]["id"] # the facebook ID of the person sending you the message

                if messaging_event.get("message"):  # someone sent us a message
                    log(messaging_event["message"])

                    candyDb = {
                        'Name': 'candy',
                        'Attributes': []
                    }
                    pendingReviewsDb = get_db_item(sender_id)
                    pending_review_found = "Attributes" in pendingReviewsDb

                    if "text" in messaging_event["message"]:
                        message_text = messaging_event["message"]["text"]  # the message's text
                        log("message text: " + message_text)

                        if message_text in candyCategory:
                            send_candy_options(sender_id, message_text)
                            return "ok", 200
                        elif RepresentsInt(message_text) and pending_review_found:
                            starRating = int(message_text)
                            if starRating < 4:
                                options = build_quick_replies_from_dict(
                                    newReviewActions,
                                    "I'm sorry your candy experience was not to your complete satisfaction. If you'd like to tell us how we could improve, click 'Continue Review' or just type what you'd like."
                                )
                                bot.send_message(sender_id, options)
                            else:
                                options = build_quick_replies_from_dict(
                                    newReviewActions,
                                    "I'm happy to hear you enjoyed your candy! If you'd like to let us know what you thought was GREAT about it, click 'Continue Review' or just type what you'd like."
                                )
                                bot.send_message(sender_id, options)
                            return "ok", 200
                        elif message_text in newReviewActions:
                            if message_text == "Continue Review":
                                if "Attributes" not in pendingReviewsDb or "Value" not in pendingReviewsDb["Attributes"][0]:
                                    continue
                                reviewQuestionPlace = int(pendingReviewsDb["Attributes"][0]["Value"])
                                log("reviewQuestionPlace: " + str(reviewQuestionPlace))
                                if reviewQuestionPlace >= len(cdv):
                                    reviewQuestionPlace = 0
                                options = build_quick_replies_from_dict(
                                    cdv[reviewQuestionPlace][1],
                                    cdv[reviewQuestionPlace][0]
                                )
                                increment_cdv_counter(sender_id, pendingReviewsDb)
                                log("Logging options")
                                log(options)
                                bot.send_message(sender_id, options)
                            elif message_text == "Complete Review":
                                if "Attributes" in pendingReviewsDb:
                                    send_message(sender_id, "Thanks for your honest review.  We will ping you when other exclusive offers are available.")
                                    sdb.delete_attributes(
                                        DomainName = domainName,
                                        ItemName = sender_id
                                    )
                            return "ok", 200


                        response = get_db_item('candy')
                        candy_found = False
                        candy = find_in_db_attributes(response, message_text)

                        if candy is not None:
                            num_available_candies = int(candy["Value"])
                            candy_found = num_available_candies > 0
                        if candy_found:
                            decrement_candies(candy, candyDb, num_available_candies, response)
                            user_info = get_user_info(sender_id)
                            send_candy_sample_request(sender_id, message_text, user_info)
                            send_message(sender_id, "Thanks for choosing your candy.  Your candy is en route for delivery.")
                        elif pending_review_found:
                            if "Attributes" not in pendingReviewsDb or "Value" not in pendingReviewsDb["Attributes"][0]:
                                continue
                            reviewQuestionPlace = int(pendingReviewsDb["Attributes"][0]["Value"])
                            log("reviewQuestionPlace: " + str(reviewQuestionPlace))
                            if reviewQuestionPlace >= len(cdv):
                                options = build_quick_replies_from_dict(
                                    ongoingReviewActions,
                                    "Thanks, we will include that with your responses!"
                                )
                            else:
                                options = build_quick_replies_from_dict(
                                    newReviewActions,
                                    "Thanks, we will include that with your responses!"
                                )
                            bot.send_message(sender_id, options)
                            return "ok", 200
                        else:
                            send_message(sender_id, "We're sorry, your choice of '" + message_text + "' is not currently available.")
                            send_quick_reply(sender_id, {})

                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("optin"):  # optin confirmation
                    pass

                if messaging_event.get("postback") or messaging_event.get("referral"):  # user clicked/tapped "postback" button in earlier message
                    log("Referral or postback")
                    log(messaging_event)
                    send_quick_reply(sender_id, {})

    return "ok", 200

@app.route('/solicit-review', methods=['GET'])
def solicit_review():
    sender_id = request.args.get('senderId')
    candy = request.args.get('candy')
    user_info = get_user_info(sender_id)
    request_message = "Hello " + user_info["first_name"] + ",\nHow would you rate your " + candy + "?"
    log("Request message: " + request_message)
    pending_reviews = get_db_item(sender_id)
    pending_reviews_attributes = []
    if "Attributes" in pending_reviews:
        pending_reviews_attributes = pending_reviews["Attributes"]
    log(pending_reviews_attributes)
    pending_reviews_attributes.append(
        {
            'Name': candy,
            'Value': str(0)
        }
    )

    sdb.put_attributes(
        DomainName = "steven.hernandez",
        ItemName = sender_id,
        Attributes = pending_reviews_attributes
    )
    sdb.put_attributes(
        DomainName = domainName,
        ItemName = candy.lower(),
        Attributes = [{
            'Name': sender_id,
            'Value': str(0)
        }]
    )
    quick_replies = [
        {
            "content_type":"text",
            "title":"1",
            "payload":"1 star",
            "image_url":"https://cdn4.iconfinder.com/data/icons/small-n-flat/24/star-128.png"
        },
        {
            "content_type":"text",
            "title":"2",
            "payload":"2 stars",
            "image_url":"https://cdn4.iconfinder.com/data/icons/small-n-flat/24/star-128.png"
        },
        {
            "content_type":"text",
            "title":"3",
            "payload":"3 stars",
            "image_url":"https://cdn4.iconfinder.com/data/icons/small-n-flat/24/star-128.png"
        },
        {
            "content_type":"text",
            "title":"4",
            "payload":"4 stars",
            "image_url":"https://cdn4.iconfinder.com/data/icons/small-n-flat/24/star-128.png"
        },
        {
            "content_type":"text",
            "title":"5",
            "payload":"5 stars",
            "image_url":"https://cdn4.iconfinder.com/data/icons/small-n-flat/24/star-128.png"
        }
    ]
    bot.send_message(sender_id, {"text": request_message, "quick_replies": quick_replies})
    return "ok", 200

def increment_cdv_counter(sender_id, pendingReviewsDb):
    pending_review_found = {
        "Name":pendingReviewsDb["Attributes"][0]["Name"]
    }
    pending_review_found["Value"] = str(int(pendingReviewsDb["Attributes"][0]["Value"]) + 1)

    pending_reviews_attributes = []
    pending_reviews_attributes.append(
        {
            'Name': pending_review_found["Name"],
            'Value': pending_review_found["Value"],
            'Replace': True
        }
    )
    sdb.put_attributes(
        DomainName = "steven.hernandez",
        ItemName = sender_id,
        Attributes = pending_reviews_attributes
    )

def decrement_candies(candy, candyDb, num_available_candies, response):
    log("found candy: ")
    log(candy)
    candy["Value"] =  str(num_available_candies - 1)
    candy["Replace"] = True
    candyDb["Attributes"] = response["Attributes"]
    sdb.batch_put_attributes(
        DomainName = domainName,
        Items = [candyDb]
    )

def send_candy_sample_request(sender_id, message_text, user_info):
    candy_request = {"senderId": sender_id, "choice": message_text, "name": user_info['first_name'] + " " + user_info['last_name']}
    r = requests.post("https://iimhlox1ml.execute-api.us-east-1.amazonaws.com/hackathon/candy-request?requestId=gibberish", data=json.dumps(candy_request))


def get_user_info(sender_id):
    url = "https://graph.facebook.com/v2.6/" + sender_id + "?fields=first_name,last_name,profile_pic,locale,timezone,gender&access_token=EAAD0GgditLsBADZAkcimL0Geyg9r9VyGFvCGoVFm5YhNlZCw3fliqbqXZB5lWnNJnGSm5oMLZCZBZCuRSHqHMgyBimmDl09MVZCcOAmnspRxsGYVTqIsleWogSAeaWvQXDcmr7rqlZAW962UgdgEwTNrDaTTqhQHqhas1I3KcYwRxwZDZD"
    info = requests.get(url)
    #log(url)
    #log(info.json())
    return info.json()

def send_quick_reply(recipient_id, options):
    info = get_user_info(recipient_id)

    options = {
        "text": "Hi " + info["first_name"] + ", Thank you for joining the TryIt Community.  We know you have a sweet tooth, and want you to be one of the first people to try the latest Candy for 2018.  In exchange we would love to hear what you think after trying the Candy.  What type of candy do you want to try?",
        "quick_replies":[]
    }
    for key in candyCategory:
        options['quick_replies'].append({
            "content_type":"text",
            "title":key,
            "payload":key,
            "image_url":"https://cdn0.iconfinder.com/data/icons/food-volume-1-4/48/78-512.png"
        })

    log("You should get a message")
    bot.send_message(recipient_id, options)


def send_message(recipient_id, message_text):

    log("sending message to {recipient}: {text}".format(recipient=recipient_id, text=message_text))

    params = {
        "access_token": "EAAD0GgditLsBAEOaCmRSpSHZCcer6BsGNizdj0KPiodpsNWK1a76s9GBDfiUk5uPVWKqOdEM3WnAeJSGQs68tYA4obE56pRCr7GvQr1B7E6W6giAxEIQxZBA7ZA0HVkrtoj3NiOHT1JZCqvDzRcfFVfk87MbVWpowF0H1mEOogZDZD"
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, data=data)
    if r.status_code != 200:
        log(r.status_code)
        log(r.text)

def find_in_db_attributes(response, keyToFind):
    #log("find_in_db_attributes: " + keyToFind)
    #log(response)
    for item in response["Attributes"]:
        if item["Name"].lower() == keyToFind.lower():
            return item

    return None

def send_candy_options(recipient_id, category):

    response = sdb.get_attributes(
        DomainName = domainName,
        ItemName = 'candy'
    )
    available_candies = {}

    for candy_name in candyCategory[category]:
        candy_db_entity = find_in_db_attributes(response, candy_name)
        if candy_db_entity is not None:
            db_candy_name = candy_db_entity["Name"]
            candy_history = sdb.get_attributes(
                DomainName = domainName,
                ItemName = candy_name.lower()
            )
            if "Attributes" in candy_history:
                already_had = find_in_db_attributes(candy_history, recipient_id)
            else:
                already_had = None
            if candy_name.lower() == db_candy_name.lower() and int(candy_db_entity["Value"]) > 0 and already_had is None:
                available_candies[candy_name] = category

    options = build_quick_replies_from_dict(
    available_candies,
    "Which candy would you like to sample?",
    "https://cdn0.iconfinder.com/data/icons/food-volume-1-4/48/78-512.png"
    )
    bot.send_message(recipient_id, options)

def build_quick_replies_from_dict(target_dict, base_level_text, image_url=None):
    options = {
        "text": base_level_text,
        "quick_replies":[]
    }
    for key in target_dict:
        option = {
            "content_type":"text",
            "title":key,
            "payload":key
        }
        if image_url is not None:
            option["image_url"] = image_url
        options['quick_replies'].append(option)
    return options

def log(message):  # simple wrapper for logging to stdout on heroku
    print str(message)
    sys.stdout.flush()

def RepresentsInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def get_db_item(name, domainName='steven.hernandez'):
    response = sdb.get_attributes(
                DomainName = domainName,
                ItemName = name
            )
    #log("get_attributes response:")
    #log(response)
    return response


if __name__ == '__main__':
    app.run(debug=True)
