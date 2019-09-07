#!/usr/local/bin/python3
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, redirect, make_response  # noqa:E402
from flask_socketio import SocketIO  # noqa:E402
from authenticate import auth  # noqa:E402
import messages  # noqa:E402
import refactor as rf  # noqa:E402
# import time  # noqa:E402
from bs4 import BeautifulSoup  # noqa:E402
import os  # noqa:E402
import peewee  # noqa:E402
from playhouse.reflection import generate_models  # noqa:E402
import urllib.parse as urlparse  # noqa:E402
from flask_login import LoginManager, current_user, login_user, login_required, logout_user  # noqa:E402,E501
import pypay  # noqa:E402
from datetime import datetime, timedelta, date  # noqa:E402
import requests  # noqa:E402
import heroku3  # noqa:E402

HEROKU_CONN = heroku3.from_key('')
TRANSACTION_TRENDS = HEROKU_CONN.apps()[""]
db = None
print("ENVIRON:")
print(os.environ)
if 'HEROKU' in os.environ:
    urlparse.uses_netloc.append('postgres')
    url = urlparse.urlparse(os.environ["DATABASE_URL"])
    db = peewee.PostgresqlDatabase(database=url.path[1:],
                                   user=url.username,
                                   password=url.password,
                                   host=url.hostname,
                                   port=url.port)


models = generate_models(db)

app = Flask(__name__)
app.secret_key = ""

socket = SocketIO(app, logger=True, engineio_logger=True, async_mode="eventlet")
login_manager = LoginManager()
login_manager.init_app(app)

USERS = models["Users"]
PLAYERS = models["Players"]


class User(object):
    def __init__(self, user, active):
        self.user = user
        self.active = active

    def is_active(self):
        return self.active

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True

    def get_id(self):
        return str(self.user.id)


@login_manager.user_loader
def load_user(user_id):
    return User(USERS.get(id=int(user_id)), True)


@app.route("/")
def index():
    print(current_user)
    if current_user.is_authenticated:
        if current_user.user.exp_date < date.today():
            resp = make_response(render_template("feed.html", date=True))
        else:
            resp = make_response(render_template("feed.html", date=False))
    else:
        resp = make_response(render_template("start.html", date=False))
    return resp


@app.route("/cancel")
def cancel():
    return render_template("cancel.html")


@app.route("/renew")
def renew():
    resp = make_response(render_template("renew.html"))
    resp.set_cookie("email", current_user.user.email)
    return resp


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route("/update")
@login_required
def update():
    return render_template("update.html")


@app.route("/update_user", methods=["POST"])
@login_required
def update_user():
    user_exists = list(USERS.select().where(((models["Users"].email == request.form["email"]) | (models["Users"].phonenum == request.form["phonenum"])) & (models["Users"].id != current_user.user.id)).execute())  # noqa:E501
    if len(user_exists) > 0:
        return render_template("exists.html", signup=False)
    else:
        USERS.update(
            email=request.form["email"],
            first_name=request.form["first_name"],
            password=request.form["password"],
            last_name=request.form["last_name"],
            phonenum=request.form["phonenum"],
            carrier=request.form["carrier"],
            trigger_limit=request.form["trigger_limit"]
            ).where(USERS.id == current_user.user.id).execute()  # noqa
        return redirect("/")


@app.route("/login_user", methods=["POST"])
def log_in():
    if current_user.is_authenticated:
        return redirect("/")
    else:
        try:
            requested_user = USERS.get(email=request.form["email"])
            print(request.form)
            if requested_user.password != request.form["password"]:
                return redirect("/invalid")
            else:
                requested_user = User(requested_user, True)
                if "remember_me" in request.form.keys():
                    print("REMEMBER ME CLICKED")
                    login_user(requested_user, remember=True)
                else:
                    login_user(requested_user, remember=False)
                return redirect("/")
        except peewee.DoesNotExist:
            return redirect("/invalid")


@app.route("/delete")
@login_required
def delete():
    current_user.user.delete_instance()
    logout_user()
    return(redirect("/"))


@app.route("/invalid")
def invalid():
    return render_template("invalid.html")


@app.route("/tos")
def privacy():
    return render_template("privacy.html")


@app.route("/db_check", methods=["POST"])
def db_check():
    user_exists = list(USERS.select().where((models["Users"].email == request.form["email"]) | (models["Users"].phonenum == request.form["phonenum"])).execute())  # noqa:E501
    if len(user_exists) > 0:
        return render_template("exists.html", signup=True)
    else:
        date = datetime.now()-timedelta(days=1)
        USERS.create(
            email=request.form["email"],
            first_name=request.form["first_name"],
            password=request.form["password"],
            last_name=request.form["last_name"],
            phonenum=request.form["phonenum"],
            carrier=request.form["carrier"],
            trigger_limit=request.form["trigger_limit"],
            exp_date=date
        )
        resp = make_response(redirect("/paynow"))
        resp.set_cookie("email", request.form["email"])
        return resp


@app.route("/paynow")
def paynow():
    return render_template("paynow.html")


@app.route("/confirm", methods=["GET"])
def confirm():
    if "tx" in request.args:
        tx = str(request.args.get("tx"))
        sub = pypay.pdt_confirm(tx, "")
        if sub.confirmed:
            date = "2019-12-31"
            USERS.update(exp_date=date, active=True).where(USERS.email == request.cookies.get("email")).execute()  # noqa
            return redirect("/")
        else:
            return redirect("/cancel")

    return redirect("/")


@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/admin")
@login_required
def admin():
    if current_user.user.admin_account is False:
        return render_template("notadmin.html")
    else:
        return render_template("admin.html")


@app.route("/adminplayers")
@login_required
def adminplayers():
    if current_user.user.admin_account is False:
        return render_template("notadmin.html")
    else:
        players = list(PLAYERS.select())
        return render_template("adminplayers.html", players=players)


@app.route("/adminusers")
@login_required
def adminusers():
    if current_user.user.admin_account is False:
        return render_template("notadmin.html")
    else:
        users = list(USERS.select())
        return render_template("adminusers.html", users=users)


@app.route("/disable")
def disable():
    USERS.update(
            active=False
            ).where(USERS.id == current_user.user.id).execute()  # noqa
    return redirect("/")


@app.route("/enable")
def enable():
    USERS.update(
            active=True
            ).where(USERS.id == current_user.user.id).execute()  # noqa
    return redirect("/")


def run():
    socket.run(app, host="0.0.0.0", port=port)


def progressbar(adds, drops):
    adds = int(adds)
    drops = int(drops)
    total = adds + drops
    max_len = 20
    len = max_len
    adds_mod = int((len/total) * adds)
    drops_mod = int((len/total) * drops)
    return_str = "["
    print("[", end="")
    for i in range(0, adds_mod):  # noqa
        print("#", end="")
        return_str += "+"
    for i in range(0, drops_mod):
        print("=", end="")
        return_str += "-"
    print("]", end="")
    return_str += "]"
    return return_str


def main():
    while True:
        try:
            now = datetime.now()
            print(now)
            while (now.hour == 3 and (now.minute == 0 or now.minute == 1 or now.minute == 2 or now.minute == 3)):  # noqa
                PLAYERS.delete().execute()
                eventlet.sleep(120)
                TRANSACTION_TRENDS.restart()
            response = requests.get("https://football.fantasysports.yahoo.com/f1/buzzindex")
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find("table", {"class": "Tst-table Table"})
            body = table.find("tbody")
            rows = body.findAll("tr")
            for row in rows:
                columns = row.findAll("td")
                player_name = columns[0].find("a", {"class": "Nowrap"}).text
                drops = columns[1].find("div").text
                adds = columns[2].find("div").text
                trades = columns[3].find("div").text
                total = columns[4].find("div").text
                player_name = rf.refactor(player_name)
                player_exists = list(PLAYERS.select().where(models["Players"].player_name == player_name).execute())  # noqa:E501
                if len(player_exists) > 0:
                    current_player = PLAYERS.get(player_name=player_name)
                    PLAYERS.update(
                        player_name=player_name,
                        adds=int(adds),
                        drops=int(drops),
                        trades=int(trades),
                        total=int(total),
                        called=current_player.called
                    ).where(PLAYERS.player_name == player_name).execute()
                else:
                    PLAYERS.create(
                        player_name=player_name,
                        adds=int(adds),
                        drops=int(drops),
                        trades=int(trades),
                        total=int(total),
                        called=[]
                    )
            all_users = list(USERS.select().where(USERS.active == True).execute())  # noqa
            for user in all_users:
                if user.exp_date >= date.today():
                    valid_players = list(PLAYERS.select().where((PLAYERS.adds >= int(user.trigger_limit)) | (PLAYERS.drops >= int(user.trigger_limit))).execute())  # noqa
                    for player in valid_players:
                        called_list = player.called
                        if user.phonenum not in called_list:
                            called_list.append(user.phonenum)
                            PLAYERS.update(called=called_list).where(PLAYERS.player_name == player.player_name).execute()  # noqa
                            output = f"{player.player_name} => adds: {player.adds},"\
                                     f" drops: {player.drops},"\
                                     f" trades:{player.trades}, total transactions: {player.total}"
                            output = output.encode("utf-8").decode("utf-8")
                            bar = progressbar(player.adds, player.drops)
                            output = output+"\n"+bar
                            recipient = user.phonenum.replace("-", "")
                            if user.carrier == "AT&T":
                                recipient = recipient+"@txt.att.net"
                            elif user.carrier == "T-Mobile":
                                recipient = recipient+"@tmomail.net"
                            elif user.carrier == "Sprint":
                                recipient = recipient+"@messaging.sprintpcs.com"
                            elif user.carrier == "Verizon":
                                recipient = recipient+"@vtext.com"
                            elif user.carrier == "Virgin Mobile":
                                recipient = recipient+"@vmobl.com"
                            msg = messages.create_message(
                                sender="transaction.trends@gmail.com",
                                to=recipient,
                                subject="",
                                msgPlain=output)
                            messages.send_message(service, "me", msg)
            eventlet.sleep(60)
        except Exception as E:
            print(E)
            eventlet.sleep(60)
            TRANSACTION_TRENDS.restart()
    TRANSACTION_TRENDS.restart()
    return 1


service = auth()
val = eventlet.spawn(main)
if val == 1:
    TRANSACTION_TRENDS.restart()
print("START")
port = int(os.environ.get('PORT', 8000))
print(port)


if __name__ == "__main__":
    socket.run(app, host="0.0.0.0", port=port)
