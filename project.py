import streamlit as st
import sqlite3
import pandas as pd
import json
import hashlib
from datetime import datetime



def get_db_connection():
    conn = sqlite3.connect('restaurant.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE, mobile TEXT UNIQUE, password_hash TEXT, role TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS menu (id INTEGER PRIMARY KEY, name TEXT UNIQUE, price REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer_email TEXT, items_json TEXT, total_price REAL, status TEXT, timestamp DATETIME)')
    conn.commit()
    conn.close()



def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_password(hashed_password, provided_password):
    return hashed_password == hash_password(provided_password)



def create_user(email, mobile, password, role):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (email, mobile, password_hash, role) VALUES (?, ?, ?, ?)", (email, mobile, hash_password(password), role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def check_login(email_or_mobile, password):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ? OR mobile = ?", (email_or_mobile, email_or_mobile)).fetchone()
    conn.close()
    if user and check_password(user['password_hash'], password):
        return user
    return None



def get_menu_items():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM menu", conn)
    conn.close()
    return df



def place_order(customer_email, items_dict, total_price):
    conn = get_db_connection()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO orders (customer_email, items_json, total_price, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                (customer_email, json.dumps(items_dict), total_price, "Pending", timestamp))
    conn.commit()
    conn.close()

def get_orders_by_customer(customer_email, status_list):
    conn = get_db_connection()
    query = f"SELECT * FROM orders WHERE customer_email = ? AND status IN ({','.join('?'*len(status_list))}) ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn, params=(customer_email, *status_list))
    conn.close()
    return df

def get_all_orders():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY timestamp DESC", conn)
    conn.close()
    return df

def update_order_status(order_id, new_status):
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()



st.set_page_config(page_title="Restaurant RMS", layout="centered")
st.title("🍽️ Restaurant Management System")
create_tables()



def show_login_page():
    auth_choice = st.sidebar.radio("Welcome", ["Login", "Sign Up"])
    
    if auth_choice == "Login":
        st.subheader("🔐 Login")
        email_or_mobile = st.text_input("Email or Mobile")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = check_login(email_or_mobile, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.role = user['role']
                st.session_state.email = user['email']
                st.rerun()
            else:
                st.error("Invalid credentials")
                
    elif auth_choice == "Sign Up":
        st.subheader("Create Account")
        email = st.text_input("Email")
        mobile = st.text_input("Mobile")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["customer", "admin"])
        if st.button("Create Account"):
            if create_user(email, mobile, password, role):
                st.success("Account created! Please log in.")
            else:
                st.error("Email or mobile already in use")



def show_admin_panel():
    st.sidebar.title("👨‍🍳 Admin Menu")
    choice = st.sidebar.radio("Select Action", ["Dashboard", "Manage Menu", "View Orders", "Logout"])

    if choice == "Dashboard":
        st.header("📈 Admin Dashboard")
        orders_df = get_all_orders()
        st.metric("Total Orders", len(orders_df))
        st.metric("Total Revenue", f"₹{orders_df[orders_df['status'] == 'Paid']['total_price'].sum():.2f}")
        
    elif choice == "Manage Menu":
        st.header("📋 Manage Menu")
        with st.form("add_item", clear_on_submit=True):
            name = st.text_input("Item Name")
            price = st.number_input("Price (₹)", min_value=0.01)
            if st.form_submit_button("Add Item"):
                conn = get_db_connection()
                try:
                    conn.execute("INSERT INTO menu (name, price) VALUES (?, ?)", (name, price))
                    conn.commit()
                    st.success(f"Added {name}")
                except sqlite3.IntegrityError:
                    st.error("Item already exists")
                finally:
                    conn.close()
        
        st.divider()
        menu_df = get_menu_items()
        for _, row in menu_df.iterrows():
            st.write(f"**{row['name']}** - ₹{row['price']}")
            if st.button("Delete", key=f"del_{row['id']}"):
                conn = get_db_connection()
                conn.execute("DELETE FROM menu WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()

    elif choice == "View Orders":
        st.header("🧾 All Orders")
        orders_df = get_all_orders()
        status_options = ["Pending", "In Progress", "Completed", "Paid"]
        
        for _, order in orders_df.iterrows():
            st.subheader(f"Order {order['id']} ({order['customer_email']}) - ₹{order['total_price']}")
            items = json.loads(order['items_json'])
            for name, qty in items.items():
                st.write(f"- {qty} x {name}")
            
            new_status = st.selectbox("Status", status_options, index=status_options.index(order['status']), key=f"status_{order['id']}")
            if new_status != order['status']:
                update_order_status(order['id'], new_status)
                st.rerun()
            st.divider()
            
    elif choice == "Logout":
        st.session_state.clear()
        st.rerun()



def show_customer_panel():
    st.sidebar.title("🍴 Customer Menu")
    choice = st.sidebar.radio("Select Action", ["Place Order", "My Active Orders", "Pay Bill", "Order History", "Logout"])

    if choice == "Place Order":
        st.header("🛒 Place an Order")
        menu_df = get_menu_items()
        if menu_df.empty:
            st.warning("Menu is empty.")
            return

        with st.form("order_form"):
            order_items = {}
            total_price = 0
            for _, item in menu_df.iterrows():
                qty = st.number_input(f"{item['name']} (₹{item['price']})", min_value=0, step=1, key=f"qty_{item['id']}")
                if qty > 0:
                    order_items[item['name']] = qty
                    total_price += item['price'] * qty
            
            if st.form_submit_button("Confirm Order"):
                if order_items:
                    place_order(st.session_state.email, order_items, total_price)
                    st.success(f"Order placed! Total: ₹{total_price}")
                else:
                    st.warning("No items selected")

    elif choice == "My Active Orders":
        st.header("🧾 My Active Orders")
        orders_df = get_orders_by_customer(st.session_state.email, ["Pending", "In Progress"])
        if orders_df.empty:
            st.info("No active orders.")
        for _, order in orders_df.iterrows():
            st.subheader(f"Order {order['id']} - {order['status']}")
            st.write(f"Total: ₹{order['total_price']} | Placed: {order['timestamp']}")
            items = json.loads(order['items_json'])
            for name, qty in items.items():
                st.write(f"- {qty} x {name}")
            st.divider()

    elif choice == "Pay Bill":
        st.header("💰 Pay Bill")
        orders_to_pay = get_orders_by_customer(st.session_state.email, ["Completed"])
        
        if orders_to_pay.empty:
            st.info("No bills ready for payment.")
            return

        total_due = orders_to_pay['total_price'].sum()
        st.subheader(f"Total Amount Due: ₹{total_due:.2f}")
        for _, order in orders_to_pay.iterrows():
            st.write(f"Order {order['id']} - ₹{order['total_price']}")
        
        if st.button("Pay Now (Show QR)"):
            st.session_state.show_qr = True
        
        if st.session_state.get("show_qr"):
            st.warning("Please scan to pay.")
            try:
                st.image("qr.jpg", width=200) 
            except:
                st.error("qr.jpg image not found")
            
            if st.button("✅ I Have Paid"):
                for order_id in orders_to_pay['id']:
                    update_order_status(order_id, "Paid")
                st.session_state.show_qr = False
                st.success("Payment confirmed!")
                st.rerun()

    elif choice == "Order History":
        st.header("📚 Order History")
        orders_df = get_orders_by_customer(st.session_state.email, ["Paid"])
        if orders_df.empty:
            st.info("No paid orders found.")
        for _, order in orders_df.iterrows():
            st.subheader(f"Order {order['id']} - Paid")
            st.write(f"Total: ₹{order['total_price']} | Paid on: {order['timestamp']}")
            items = json.loads(order['items_json'])
            for name, qty in items.items():
                st.write(f"- {qty} x {name}")
            st.divider()
            
    elif choice == "Logout":
        st.session_state.clear()
        st.rerun()

if not st.session_state.get("logged_in"):
    show_login_page()
else:
    if st.session_state.role == "admin":
        show_admin_panel()
    else:
        show_customer_panel()