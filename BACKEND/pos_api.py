import os
from datetime import datetime, timedelta
from functools import wraps
from uuid import uuid4
import shutil

from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import func, text
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///pos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_EXPIRATION_HOURS'] = 24

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------------------------
# Models (all as before)
# ---------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='cashier')
    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'full_name': self.full_name,
            'created_at': self.created_at.isoformat()
        }

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'description': self.description}

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    buying_price = db.Column(db.Numeric(10,2), default=0)
    selling_price = db.Column(db.Numeric(10,2), nullable=False)
    quantity_in_stock = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=5)
    unit = db.Column(db.String(20), default='pcs')
    supplier = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Category', backref='products')

    def to_dict(self):
        return {
            'id': self.id,
            'barcode': self.barcode,
            'name': self.name,
            'category': self.category.name if self.category else None,
            'category_id': self.category_id,
            'buying_price': float(self.buying_price),
            'selling_price': float(self.selling_price),
            'quantity_in_stock': self.quantity_in_stock,
            'min_stock': self.min_stock,
            'unit': self.unit,
            'supplier': self.supplier,
            'created_at': self.created_at.isoformat()
        }

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    subtotal = db.Column(db.Numeric(10,2), default=0)
    discount = db.Column(db.Numeric(10,2), default=0)
    tax = db.Column(db.Numeric(10,2), default=0)
    total = db.Column(db.Numeric(10,2), nullable=False)
    payment_method = db.Column(db.String(50))
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)

    cashier = db.relationship('User', backref='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'invoice_no': self.invoice_no,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'subtotal': float(self.subtotal),
            'discount': float(self.discount),
            'tax': float(self.tax),
            'total': float(self.total),
            'payment_method': self.payment_method,
            'cashier': self.cashier.full_name if self.cashier else None,
            'sale_date': self.sale_date.isoformat(),
            'items': [item.to_dict() for item in self.items]
        }

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10,2), nullable=False)
    total = db.Column(db.Numeric(10,2), nullable=False)

    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'unit_price': float(self.unit_price),
            'total': float(self.total)
        }

class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    movement_type = db.Column(db.String(20))
    quantity = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'created_at': self.created_at.isoformat()
        }

class Return(db.Model):
    __tablename__ = 'returns'
    id = db.Column(db.Integer, primary_key=True)
    original_invoice = db.Column(db.String(50), nullable=False)
    return_invoice = db.Column(db.String(50), unique=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer, nullable=False)
    refund_amount = db.Column(db.Numeric(10,2), nullable=False)
    reason = db.Column(db.String(200))
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    return_date = db.Column(db.DateTime, default=datetime.utcnow)

    cashier = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'original_invoice': self.original_invoice,
            'return_invoice': self.return_invoice,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'refund_amount': float(self.refund_amount),
            'reason': self.reason,
            'cashier': self.cashier.full_name if self.cashier else None,
            'return_date': self.return_date.isoformat()
        }

class LoyaltyCustomer(db.Model):
    __tablename__ = 'loyalty_customers'
    phone = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    points = db.Column(db.Integer, default=0)
    total_spent = db.Column(db.Numeric(10,2), default=0)
    tier = db.Column(db.String(20), default='Bronze')
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'phone': self.phone,
            'name': self.name,
            'points': self.points,
            'total_spent': float(self.total_spent),
            'tier': self.tier,
            'joined_date': self.joined_date.isoformat()
        }

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10,2), nullable=False)
    description = db.Column(db.Text)
    expense_date = db.Column(db.Date, default=datetime.utcnow().date)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'amount': float(self.amount),
            'description': self.description,
            'expense_date': self.expense_date.isoformat(),
            'user': self.user.full_name if self.user else None,
            'created_at': self.created_at.isoformat()
        }

class Setting(db.Model):
    __tablename__ = 'settings'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

    def to_dict(self):
        return {'key': self.key, 'value': self.value}

class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    total_sales = db.Column(db.Numeric(10,2), default=0)
    status = db.Column(db.String(20), default='active')

    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'cashier_name': self.user.full_name if self.user else None,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_sales': float(self.total_sales),
            'status': self.status
        }

# ---------------------------
# Authentication helper
# ---------------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            token = token.split(' ')[1]
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = User.query.get(payload['user_id'])
            if not user:
                return jsonify({'error': 'User not found'}), 401
            g.current_user = user
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if g.current_user.role not in allowed_roles:
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# ---------------------------
# API Endpoints
# ---------------------------
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/api/users/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    user = User(
        username=data['username'],
        full_name=data['full_name'],
        role=data.get('role', 'cashier')
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201

@app.route('/api/users/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode(
        {'user_id': user.id, 'exp': datetime.utcnow() + timedelta(hours=app.config['JWT_EXPIRATION_HOURS'])},
        app.config['SECRET_KEY'],
        algorithm='HS256'
    )
    return jsonify({'token': token, 'user': user.to_dict()})

@app.route('/api/users', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def get_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@token_required
@role_required(['admin'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == g.current_user.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200

@app.route('/api/products', methods=['GET'])
@token_required
def get_products():
    products = Product.query.all()
    return jsonify([p.to_dict() for p in products])

@app.route('/api/products', methods=['POST'])
@token_required
@role_required(['admin', 'manager'])
def create_product():
    data = request.json
    barcode = data.get('barcode') or str(uuid4().int)[:13]
    product = Product(
        barcode=barcode,
        name=data['name'],
        category_id=data.get('category_id'),
        buying_price=data.get('buying_price', 0),
        selling_price=data['selling_price'],
        quantity_in_stock=data.get('quantity_in_stock', 0),
        min_stock=data.get('min_stock', 5),
        unit=data.get('unit', 'pcs'),
        supplier=data.get('supplier', '')
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict()), 201

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@token_required
@role_required(['admin', 'manager'])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json
    product.name = data.get('name', product.name)
    product.buying_price = data.get('buying_price', product.buying_price)
    product.selling_price = data.get('selling_price', product.selling_price)
    product.quantity_in_stock = data.get('quantity_in_stock', product.quantity_in_stock)
    product.min_stock = data.get('min_stock', product.min_stock)
    product.unit = data.get('unit', product.unit)
    product.supplier = data.get('supplier', product.supplier)
    if 'category_id' in data:
        product.category_id = data['category_id']
    db.session.commit()
    return jsonify(product.to_dict())

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@token_required
@role_required(['admin'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'}), 200

@app.route('/api/invoices', methods=['POST'])
@token_required
def create_invoice():
    data = request.json
    today = datetime.utcnow().strftime('%Y%m%d')
    last_inv = Invoice.query.filter(Invoice.invoice_no.like(f'INV-{today}-%')).order_by(Invoice.id.desc()).first()
    seq = int(last_inv.invoice_no.split('-')[-1]) + 1 if last_inv else 1
    invoice_no = f"INV-{today}-{seq:04d}"

    invoice = Invoice(
        invoice_no=invoice_no,
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        subtotal=data['subtotal'],
        discount=data.get('discount', 0),
        tax=data.get('tax', 0),
        total=data['total'],
        payment_method=data.get('payment_method', 'Cash'),
        cashier_id=g.current_user.id
    )
    db.session.add(invoice)
    db.session.flush()

    for item_data in data['items']:
        product = Product.query.get(item_data['product_id'])
        if not product:
            return jsonify({'error': f"Product {item_data['product_id']} not found"}), 400
        if product.quantity_in_stock < item_data['quantity']:
            return jsonify({'error': f"Insufficient stock for {product.name}"}), 400
        product.quantity_in_stock -= item_data['quantity']
        movement = StockMovement(
            product_id=product.id,
            movement_type='sale',
            quantity=item_data['quantity'],
            reason=f"Invoice {invoice_no}",
            user_id=g.current_user.id
        )
        db.session.add(movement)
        item = InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            product_name=product.name,
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            total=item_data['total']
        )
        db.session.add(item)

    db.session.commit()
    return jsonify(invoice.to_dict()), 201

@app.route('/api/invoices', methods=['GET'])
@token_required
def get_invoices():
    invoices = Invoice.query.order_by(Invoice.sale_date.desc()).all()
    return jsonify([inv.to_dict() for inv in invoices])

@app.route('/api/reports/dashboard', methods=['GET'])
@token_required
def dashboard_stats():
    today = datetime.utcnow().date()
    start_of_today = datetime(today.year, today.month, today.day)
    total_products = Product.query.count()
    low_stock = Product.query.filter(Product.quantity_in_stock <= Product.min_stock).count()
    today_sales = db.session.query(func.coalesce(func.sum(Invoice.total), 0)).filter(Invoice.sale_date >= start_of_today).scalar()
    today_transactions = Invoice.query.filter(Invoice.sale_date >= start_of_today).count()
    total_revenue = db.session.query(func.coalesce(func.sum(Invoice.total), 0)).scalar()
    top_products = db.session.query(
        Product.name, func.sum(InvoiceItem.quantity).label('qty')
    ).join(InvoiceItem, Product.id == InvoiceItem.product_id).group_by(Product.id).order_by(text('qty DESC')).limit(5).all()
    top_products_list = [{'name': p[0], 'quantity_sold': int(p[1])} for p in top_products]
    return jsonify({
        'total_products': total_products,
        'low_stock': low_stock,
        'today_sales': float(today_sales),
        'today_transactions': today_transactions,
        'total_revenue': float(total_revenue),
        'top_products': top_products_list
    })

@app.route('/api/reports/sales', methods=['GET'])
@token_required
def sales_report():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    query = db.session.query(
        func.date(Invoice.sale_date).label('date'),
        func.count(Invoice.id).label('transactions'),
        func.sum(Invoice.total).label('total')
    ).group_by(func.date(Invoice.sale_date))
    if from_date:
        query = query.filter(Invoice.sale_date >= from_date)
    if to_date:
        query = query.filter(Invoice.sale_date <= to_date)
    results = query.all()
    return jsonify([{
        'date': r.date.isoformat(),
        'transactions': r.transactions,
        'total': float(r.total)
    } for r in results])

@app.route('/api/reports/inventory', methods=['GET'])
@token_required
def inventory_report():
    products = Product.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'quantity_in_stock': p.quantity_in_stock,
        'selling_price': float(p.selling_price),
        'total_value': float(p.quantity_in_stock * p.selling_price)
    } for p in products])

# ---------- Suppliers ----------
@app.route('/api/suppliers', methods=['GET'])
@token_required
def get_suppliers():
    suppliers = Supplier.query.all()
    return jsonify([s.to_dict() for s in suppliers])

@app.route('/api/suppliers', methods=['POST'])
@token_required
@role_required(['admin', 'manager'])
def create_supplier():
    data = request.json
    supplier = Supplier(
        name=data['name'],
        contact_person=data.get('contact_person'),
        phone=data.get('phone'),
        email=data.get('email'),
        address=data.get('address')
    )
    db.session.add(supplier)
    db.session.commit()
    return jsonify(supplier.to_dict()), 201

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@token_required
@role_required(['admin', 'manager'])
def update_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.json
    supplier.name = data.get('name', supplier.name)
    supplier.contact_person = data.get('contact_person', supplier.contact_person)
    supplier.phone = data.get('phone', supplier.phone)
    supplier.email = data.get('email', supplier.email)
    supplier.address = data.get('address', supplier.address)
    db.session.commit()
    return jsonify(supplier.to_dict())

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@token_required
@role_required(['admin'])
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)
    db.session.commit()
    return jsonify({'message': 'Supplier deleted'}), 200

# ---------- Returns ----------
@app.route('/api/returns', methods=['GET'])
@token_required
def get_returns():
    returns = Return.query.order_by(Return.return_date.desc()).all()
    return jsonify([r.to_dict() for r in returns])

@app.route('/api/returns', methods=['POST'])
@token_required
def create_return():
    data = request.json
    return_inv = f"RET-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4]}"
    ret = Return(
        original_invoice=data['original_invoice'],
        return_invoice=return_inv,
        product_id=data['product_id'],
        product_name=data['product_name'],
        quantity=data['quantity'],
        refund_amount=data['refund_amount'],
        reason=data.get('reason'),
        cashier_id=g.current_user.id
    )
    product = Product.query.get(data['product_id'])
    if product:
        product.quantity_in_stock += data['quantity']
        movement = StockMovement(
            product_id=product.id,
            movement_type='return',
            quantity=data['quantity'],
            reason=f"Return for {data['original_invoice']}",
            user_id=g.current_user.id
        )
        db.session.add(movement)
    db.session.add(ret)
    db.session.commit()
    return jsonify(ret.to_dict()), 201

# ---------- Loyalty ----------
@app.route('/api/loyalty', methods=['GET'])
@token_required
def get_loyalty():
    customers = LoyaltyCustomer.query.order_by(LoyaltyCustomer.points.desc()).all()
    return jsonify([c.to_dict() for c in customers])

@app.route('/api/loyalty', methods=['POST'])
@token_required
@role_required(['admin', 'cashier'])
def add_loyalty_customer():
    data = request.json
    existing = LoyaltyCustomer.query.get(data['phone'])
    if existing:
        return jsonify({'error': 'Customer already exists'}), 400
    customer = LoyaltyCustomer(
        phone=data['phone'],
        name=data['name']
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify(customer.to_dict()), 201

@app.route('/api/loyalty/<phone>', methods=['DELETE'])
@token_required
@role_required(['admin'])
def delete_loyalty(phone):
    customer = LoyaltyCustomer.query.get_or_404(phone)
    db.session.delete(customer)
    db.session.commit()
    return jsonify({'message': 'Customer removed'}), 200

# ---------- Expenses ----------
@app.route('/api/expenses', methods=['GET'])
@token_required
def get_expenses():
    expenses = Expense.query.order_by(Expense.expense_date.desc()).all()
    return jsonify([e.to_dict() for e in expenses])

@app.route('/api/expenses', methods=['POST'])
@token_required
@role_required(['admin', 'manager'])
def add_expense():
    data = request.json
    expense = Expense(
        category=data['category'],
        amount=data['amount'],
        description=data.get('description'),
        expense_date=datetime.strptime(data['expense_date'], '%Y-%m-%d').date() if data.get('expense_date') else datetime.utcnow().date(),
        user_id=g.current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201

# ---------- Settings ----------
@app.route('/api/settings', methods=['GET'])
@token_required
@role_required(['admin'])
def get_settings():
    settings = Setting.query.all()
    return jsonify([s.to_dict() for s in settings])

@app.route('/api/settings', methods=['POST'])
@token_required
@role_required(['admin'])
def update_setting():
    data = request.json
    setting = Setting.query.get(data['key'])
    if setting:
        setting.value = data['value']
    else:
        setting = Setting(key=data['key'], value=data['value'])
        db.session.add(setting)
    db.session.commit()
    return jsonify(setting.to_dict())

# ---------- Shifts ----------
@app.route('/api/shifts', methods=['GET'])
@token_required
def get_shifts():
    shifts = Shift.query.order_by(Shift.start_time.desc()).all()
    return jsonify([s.to_dict() for s in shifts])

@app.route('/api/shifts/start', methods=['POST'])
@token_required
def start_shift():
    active = Shift.query.filter_by(user_id=g.current_user.id, status='active').first()
    if active:
        return jsonify({'error': 'You already have an active shift'}), 400
    shift = Shift(user_id=g.current_user.id, status='active')
    db.session.add(shift)
    db.session.commit()
    return jsonify(shift.to_dict()), 201

@app.route('/api/shifts/end', methods=['POST'])
@token_required
def end_shift():
    shift = Shift.query.filter_by(user_id=g.current_user.id, status='active').first()
    if not shift:
        return jsonify({'error': 'No active shift found'}), 400
    shift.end_time = datetime.utcnow()
    shift.status = 'ended'
    total = db.session.query(func.sum(Invoice.total)).filter(
        Invoice.cashier_id == g.current_user.id,
        Invoice.sale_date >= shift.start_time,
        Invoice.sale_date <= shift.end_time
    ).scalar() or 0
    shift.total_sales = total
    db.session.commit()
    return jsonify(shift.to_dict())

# ---------- Backup ----------
@app.route('/api/backup', methods=['POST'])
@token_required
@role_required(['admin'])
def backup_db():
    try:
        os.makedirs('backups', exist_ok=True)
        backup_name = f"backups/backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            shutil.copy2(db_path, backup_name)
        else:
            return jsonify({'error': 'Backup only implemented for SQLite'}), 501
        return jsonify({'message': f'Backup saved to {backup_name}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- Invoice Panel Summary ----------
@app.route('/api/invoice_panel/summary', methods=['GET'])
@token_required
def invoice_panel_summary():
    total_invoices = Invoice.query.count()
    total_quotes = 0
    pending_deliveries = 0
    return jsonify({
        'total_invoices': total_invoices,
        'total_quotes': total_quotes,
        'pending_deliveries': pending_deliveries
    })

# ---------- Receipt Records ----------
@app.route('/api/receipt_records', methods=['GET'])
@token_required
def receipt_records():
    search = request.args.get('search', '')
    query = Invoice.query
    if search:
        query = query.filter(
            db.or_(
                Invoice.invoice_no.ilike(f'%{search}%'),
                Invoice.customer_name.ilike(f'%{search}%'),
                Invoice.customer_phone.ilike(f'%{search}%')
            )
        )
    invoices = query.order_by(Invoice.sale_date.desc()).limit(100).all()
    return jsonify([{
        'invoice_no': inv.invoice_no,
        'customer_name': inv.customer_name,
        'total': float(inv.total),
        'payment_method': inv.payment_method,
        'sale_date': inv.sale_date.isoformat()
    } for inv in invoices])

# ---------------------------
# Serve Frontend
# ---------------------------
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

# ---------------------------
# Seed sample data
# ---------------------------
def seed_data():
    with app.app_context():
        if User.query.count() == 0:
            admin = User(username='manuel', full_name='Administrator', role='admin')
            admin.set_password('manuel')
            db.session.add(admin)
            cashier = User(username='cashier', full_name='Cashier User', role='cashier')
            cashier.set_password('cashier')
            db.session.add(cashier)
            db.session.commit()

        if Category.query.count() == 0:
            categories = ['Beverages', 'Snacks', 'Dairy', 'Fruits', 'Vegetables', 'Household']
            for cat in categories:
                db.session.add(Category(name=cat))
            db.session.commit()

        if Product.query.count() == 0:
            cat = Category.query.first()
            sample_products = [
                {'name': 'Coca Cola 500ml', 'selling_price': 120, 'quantity': 50, 'unit': 'bottle', 'barcode': '123456789012'},
                {'name': 'Milk 1L', 'selling_price': 85, 'quantity': 30, 'unit': 'carton', 'barcode': '234567890123'},
                {'name': 'Bread', 'selling_price': 50, 'quantity': 20, 'unit': 'loaf', 'barcode': '345678901234'},
                {'name': 'Rice 1kg', 'selling_price': 220, 'quantity': 40, 'unit': 'pack', 'barcode': '456789012345'},
            ]
            for p in sample_products:
                product = Product(
                    name=p['name'],
                    selling_price=p['selling_price'],
                    quantity_in_stock=p['quantity'],
                    unit=p['unit'],
                    barcode=p['barcode'],
                    category_id=cat.id
                )
                db.session.add(product)
            db.session.commit()

        if Supplier.query.count() == 0:
            suppliers = [
                Supplier(name='ABC Distributors', contact_person='John Doe', phone='0712345678', email='abc@mail.com', address='Nairobi'),
                Supplier(name='XYZ Wholesalers', contact_person='Jane Smith', phone='0723456789', email='xyz@mail.com', address='Mombasa')
            ]
            db.session.add_all(suppliers)
            db.session.commit()

        if LoyaltyCustomer.query.count() == 0:
            cust = LoyaltyCustomer(phone='0711111111', name='Loyal Customer', points=100, total_spent=5000)
            db.session.add(cust)
            db.session.commit()

# ---------------------------
# Run app
# ---------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') == 'development')