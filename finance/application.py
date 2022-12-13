import os
from tempfile import mkdtemp

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.exceptions import default_exceptions, HTTPException, \
    InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    if request.method == "POST":
        db.execute("""
            UPDATE users
            SET cash = cash + :amount
            WHERE id=:user_id
        """, amount=request.form.get("cash"),
                   user_id=session["user_id"])
        flash("Added Cash to Balance!")
        return redirect("/")
    else:
        return render_template("add_cash.html")


@app.route("/")
@login_required
def index():
    rows = db.execute("""
        SELECT symbol, SUM(shares) as totalShares
        FROM transactions
        WHERE user_id = :user_id
        GROUP BY symbol
        HAVING totalShares > 0;
    """, user_id=session["user_id"])
    stuffs = []
    sum_p = 0
    for row in rows:
        stock = lookup(row["symbol"])
        stuffs.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": row["totalShares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["totalShares"])
        })
        sum_p += stock["price"] * row["totalShares"]
    rows = db.execute("SELECT cash FROM users WHERE id=:user_id",
                      user_id=session["user_id"])
    possession = rows[0]["cash"]
    sum_p += possession
    return render_template("index.html", stuffs=stuffs,
                           posession=usd(possession), sum_p=usd(sum_p))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if_missing = is_provided("symbol") or is_provided("shares")
        if if_missing:
            return if_missing
        elif not request.form.get("shares").isdigit():
            return apology("Invalid Number of Shares to Buy")
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        shares = int(request.form.get("shares"))
        if stock is None:
            return apology("Invalid Symbol")
        rows = db.execute("SELECT cash FROM users WHERE id=:id",
                          id=session["user_id"])
        cash = rows[0]["cash"]
        update_money = cash - shares * stock["price"]
        if update_money < 0:
            return apology("Insufficient Balance for Purchase")
        db.execute("UPDATE users SET cash=:update_money WHERE id=:id",
                   update_money=update_money,
                   id=session["user_id"])
        db.execute("""
            INSERT INTO transactions
                (user_id, symbol, shares, price)
            VALUES (:user_id, :symbol, :shares, :price)
            """,
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   shares=shares,
                   price=stock["price"]
                   )
        flash("Purchase Successful!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("""
        SELECT symbol, shares, price, transacted
        FROM transactions
        WHERE user_id=:user_id
    """, user_id=session["user_id"])
    for x in range(len(transactions)):
        transactions[x]["price"] = usd(transactions[x]["price"])
    return render_template("history.html", transactions=transactions)


def is_provided(field):
    if not request.form.get(field):
        return apology(f"must provide {field}")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username and password were submitted
        checks = is_provided("username") or is_provided("password")
        if checks is not None:
            return checks
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"],
                                                     request.form.get(
                                                         "password")):
            return apology("Invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id by clearing session
    session.clear()

    # Redirect user to the login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        check = is_provided("symbol")
        if check is not None:
            return check
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol")
        return render_template("quoted.html", stockName={
            'name': stock['name'],
            'symbol': stock['symbol'],
            'price': usd(stock['price'])
        })
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Checks whether username, password, and its confirmation are provided
        checks = is_provided("username") or is_provided(
            "password") or is_provided("confirmation")
        if checks is not None:
            return checks
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords must match")
        try:
            # Attempts to add user to database
            prim_key = db.execute(
                "INSERT INTO users (username, hash) VALUES (:username, :hash)",
                username=request.form.get("username"),
                hash=generate_password_hash(request.form.get("password")))
        except:
            return apology("Username already exists")
        if prim_key is None:
            return apology("Registration error")
        session["user_id"] = prim_key
        redirect("/")
        return render_template("login.html")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if_missing = is_provided("symbol") or is_provided("shares")
        if if_missing:
            return if_missing
        elif not request.form.get("shares").isdigit():
            return apology("Invalid Number of Shares")
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        shares = int(request.form.get("shares"))
        if stock is None:
            return apology("Invalid Symbol")
        rows = db.execute("""
            SELECT symbol, SUM(shares) as totalShares
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING totalShares > 0;
        """, user_id=session["user_id"])
        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["totalShares"]:
                    return apology("You cannot sell that many shares")

        rows = db.execute("SELECT cash FROM users WHERE id=:id",
                          id=session["user_id"])
        cash = rows[0]["cash"]
        update_money = cash + shares * stock["price"]
        db.execute("UPDATE users SET cash=:update_money WHERE id=:id",
                   update_money=update_money,
                   id=session["user_id"])
        db.execute("""
            INSERT INTO transactions
                (user_id, symbol, shares, price)
            VALUES (:user_id, :symbol, :shares, :price)
            """,
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   shares=-1 * shares,
                   price=stock["price"]
                   )
        flash("Sold!")
        return redirect("/")

    else:
        rows = db.execute("""
            SELECT symbol
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING SUM(shares) > 0;
        """, user_id=session["user_id"])
        return render_template("sell.html",
                               symbols=[row["symbol"] for row in rows])


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
