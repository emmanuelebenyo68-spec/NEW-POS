import os
from datetime import datetime, timedelta
from functools import wraps
from uuid import uuid4
import shutil
import base64

from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import func, text, cast, Numeric
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
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max for images

if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://',
                                                                                          'postgresql://', 1)

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ---------------------------
# Models (existing + new ItemImage)
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
    buying_price = db.Column(db.Numeric(10, 2), default=0)
    selling_price = db.Column(db.Numeric(10, 2), nullable=False)
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
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)
    tax = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50))
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    cashier_display_name = db.Column(db.String(100), nullable=True)

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
            'cashier_display_name': self.cashier_display_name,
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
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)

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
    refund_amount = db.Column(db.Numeric(10, 2), nullable=False)
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
    total_spent = db.Column(db.Numeric(10, 2), default=0)
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
    amount = db.Column(db.Numeric(10, 2), nullable=False)
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
    total_sales = db.Column(db.Numeric(10, 2), default=0)
    status = db.Column(db.String(20), default='active')
    shift_display_name = db.Column(db.String(100), nullable=True)

    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'cashier_name': self.user.full_name if self.user else None,
            'shift_display_name': self.shift_display_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_sales': float(self.total_sales),
            'status': self.status
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.full_name if self.user else 'System',
            'action': self.action,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat()
        }


# NEW: ItemImage model for the image gallery
class ItemImage(db.Model):
    __tablename__ = 'item_images'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_data = db.Column(db.Text, nullable=False)  # base64 encoded image
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': float(self.price),
            'image_data': self.image_data,
            'created_at': self.created_at.isoformat()
        }


# ---------------------------
# Authentication helpers (unchanged)
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


def log_action(user_id, action, details, ip=None):
    if ip is None and request:
        ip = request.remote_addr
    log = AuditLog(user_id=user_id, action=action, details=details, ip_address=ip)
    db.session.add(log)
    db.session.commit()


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
    log_action(user.id, 'user_create', f"User {user.username} ({user.full_name}) created")
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
    log_action(user.id, 'login', f"User {user.username} logged in from IP {request.remote_addr}")
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
    log_action(g.current_user.id, 'product_create',
               f"Product {product.name} (ID {product.id}) buying {product.buying_price} selling {product.selling_price}")
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
    log_action(g.current_user.id, 'product_update', f"Product ID {product_id} updated")
    return jsonify(product.to_dict())


@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@token_required
@role_required(['admin', 'manager'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    log_action(g.current_user.id, 'product_delete', f"Product ID {product_id} {product.name}")
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

    active_shift = Shift.query.filter_by(user_id=g.current_user.id, status='active').first()
    cashier_display = active_shift.shift_display_name if active_shift and active_shift.shift_display_name else g.current_user.full_name

    invoice = Invoice(
        invoice_no=invoice_no,
        customer_name=data.get('customer_name'),
        customer_phone=data.get('customer_phone'),
        subtotal=data['subtotal'],
        discount=data.get('discount', 0),
        tax=data.get('tax', 0),
        total=data['total'],
        payment_method=data.get('payment_method', 'Cash'),
        cashier_id=g.current_user.id,
        cashier_display_name=cashier_display
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
    log_action(g.current_user.id, 'sale', f"Invoice {invoice_no} total {invoice.total}")
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
    today_sales = db.session.query(func.coalesce(func.sum(Invoice.total), 0)).filter(
        Invoice.sale_date >= start_of_today).scalar()
    today_transactions = Invoice.query.filter(Invoice.sale_date >= start_of_today).count()
    total_revenue = db.session.query(func.coalesce(func.sum(Invoice.total), 0)).scalar()

    # total cost and total profit
    total_cost = db.session.query(
        func.coalesce(func.sum(InvoiceItem.quantity * Product.buying_price), 0)
    ).join(Product, InvoiceItem.product_id == Product.id).scalar()
    total_profit = total_revenue - total_cost
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

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
        'total_cost': float(total_cost),
        'total_profit': float(total_profit),
        'profit_margin': round(float(profit_margin), 2),
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
    report = []
    for r in results:
        # Convert date safely (SQLite returns string, PostgreSQL returns date)
        if hasattr(r.date, 'isoformat'):
            date_str = r.date.isoformat()
        else:
            date_str = str(r.date)
        report.append({
            'date': date_str,
            'transactions': r.transactions,
            'total': float(r.total)
        })
    return jsonify(report)


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


# ---------- Suppliers (unchanged) ----------
@app.route('/api/suppliers', methods=['GET'])
@token_required
def get_suppliers():
    suppliers = Supplier.query.all()
    return jsonify([s.to_dict() for s in suppliers])


@app.route('/api/suppliers', methods=['POST'])
@token_required
@role_required(['admin'])
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
@role_required(['admin'])
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


# ---------- Returns (unchanged) ----------
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
    log_action(g.current_user.id, 'return',
               f"Return {return_inv} for invoice {data['original_invoice']}, product {data['product_name']}, qty {data['quantity']}")
    return jsonify(ret.to_dict()), 201


# ---------- Loyalty (unchanged) ----------
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


# ---------- Expenses (unchanged) ----------
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
        expense_date=datetime.strptime(data['expense_date'], '%Y-%m-%d').date() if data.get(
            'expense_date') else datetime.utcnow().date(),
        user_id=g.current_user.id
    )
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201


# ---------- Settings (unchanged) ----------
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


# ---------- Shifts (unchanged) ----------
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
    data = request.json or {}
    display_name = data.get('display_name', '').strip()
    if not display_name:
        display_name = g.current_user.full_name
    shift = Shift(
        user_id=g.current_user.id,
        status='active',
        shift_display_name=display_name
    )
    db.session.add(shift)
    db.session.commit()
    log_action(g.current_user.id, 'shift_start', f"Shift ID {shift.id} display name '{shift.shift_display_name}'")
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
    log_action(g.current_user.id, 'shift_end', f"Shift ID {shift.id} total sales {total}")
    return jsonify(shift.to_dict())


# ---------- Backup (unchanged) ----------
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


# ---------- Invoice Panel Summary (unchanged) ----------
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


# ---------- Receipt Records (unchanged) ----------
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


# ---------- Reset credentials (unchanged) ----------
@app.route('/reset-credentials')
def reset_credentials():
    from werkzeug.security import generate_password_hash
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.username = 'manuel'
        admin.password_hash = generate_password_hash('manuel')
        db.session.commit()
        return "Updated existing admin to manuel/manuel"
    manuel = User.query.filter_by(username='manuel').first()
    if manuel:
        manuel.password_hash = generate_password_hash('manuel')
        db.session.commit()
        return "Updated manuel password to manuel"
    else:
        new_user = User(username='manuel', full_name='Administrator', role='admin')
        new_user.set_password('manuel')
        db.session.add(new_user)
        db.session.commit()
        return "Created new manuel/manuel"


# ---------- ITEM IMAGES API (NEW) ----------
@app.route('/api/item_images', methods=['GET'])
@token_required
def get_item_images():
    images = ItemImage.query.order_by(ItemImage.created_at.desc()).all()
    return jsonify([img.to_dict() for img in images])


@app.route('/api/item_images', methods=['POST'])
@token_required
@role_required(['admin', 'manager'])
def create_item_image():
    # Expect multipart form data: name, price, image (file)
    if 'image' not in request.files:
        return jsonify({'error': 'Image file is required'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    name = request.form.get('name')
    price = request.form.get('price')
    if not name or not price:
        return jsonify({'error': 'Name and price are required'}), 400
    try:
        price = float(price)
    except ValueError:
        return jsonify({'error': 'Invalid price'}), 400

    # Convert image to base64
    img_data = base64.b64encode(file.read()).decode('utf-8')
    # Optionally add a data URL prefix for easy rendering
    img_data_url = f"data:{file.content_type};base64,{img_data}"

    new_image = ItemImage(
        name=name,
        price=price,
        image_data=img_data_url
    )
    db.session.add(new_image)
    db.session.commit()
    log_action(g.current_user.id, 'item_image_create', f"Added image: {name}")
    return jsonify(new_image.to_dict()), 201


@app.route('/api/item_images/<int:image_id>', methods=['DELETE'])
@token_required
@role_required(['admin', 'manager'])
def delete_item_image(image_id):
    image = ItemImage.query.get_or_404(image_id)
    db.session.delete(image)
    db.session.commit()
    log_action(g.current_user.id, 'item_image_delete', f"Deleted image ID {image_id}")
    return jsonify({'message': 'Image deleted'}), 200


# ---------------------------
# Serve Frontend
# ---------------------------
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')


# ---------------------------
# Add missing columns (unchanged)
# ---------------------------
def add_missing_columns():
    with app.app_context():
        inspector = db.inspect(db.engine)
        if 'shifts' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('shifts')]
            if 'shift_display_name' not in columns:
                db.session.execute(text('ALTER TABLE shifts ADD COLUMN shift_display_name VARCHAR(100)'))
                db.session.commit()
        if 'invoices' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('invoices')]
            if 'cashier_display_name' not in columns:
                db.session.execute(text('ALTER TABLE invoices ADD COLUMN cashier_display_name VARCHAR(100)'))
                db.session.commit()


# ---------------------------
# Seed sample data (unchanged)
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
            categories = ['Beverages', 'Snacks', 'Dairy', 'Fruits', 'Vegetables', 'Household', 'Grains']
            for cat in categories:
                db.session.add(Category(name=cat))
            db.session.commit()

        if Product.query.count() == 0:
            cat_beverages = Category.query.filter_by(name='Beverages').first()
            cat_snacks = Category.query.filter_by(name='Snacks').first()
            cat_dairy = Category.query.filter_by(name='Dairy').first()
            cat_fruits = Category.query.filter_by(name='Fruits').first()
            cat_veg = Category.query.filter_by(name='Vegetables').first()
            cat_household = Category.query.filter_by(name='Household').first()
            cat_grains = Category.query.filter_by(name='Grains').first()

            sample_products = [
                # Beverages
                {'name': 'Coca Cola 500ml', 'buying_price': 100, 'selling_price': 120, 'quantity': 50, 'unit': 'bottle',
                 'barcode': '123456789012', 'cat': cat_beverages},
                {'name': 'Pepsi 500ml', 'buying_price': 100, 'selling_price': 120, 'quantity': 45, 'unit': 'bottle',
                 'barcode': '123456789013', 'cat': cat_beverages},
                {'name': 'Fanta Orange 500ml', 'buying_price': 100, 'selling_price': 120, 'quantity': 40,
                 'unit': 'bottle', 'barcode': '123456789014', 'cat': cat_beverages},
                {'name': 'Sprite 500ml', 'buying_price': 100, 'selling_price': 120, 'quantity': 40, 'unit': 'bottle',
                 'barcode': '123456789015', 'cat': cat_beverages},
                {'name': 'Minute Maid Juice 1L', 'buying_price': 150, 'selling_price': 200, 'quantity': 30,
                 'unit': 'carton', 'barcode': '123456789016', 'cat': cat_beverages},
                # Dairy
                {'name': 'Fresh Milk 1L', 'buying_price': 70, 'selling_price': 85, 'quantity': 30, 'unit': 'carton',
                 'barcode': '234567890123', 'cat': cat_dairy},
                {'name': 'Yogurt 500ml', 'buying_price': 55, 'selling_price': 70, 'quantity': 25, 'unit': 'cup',
                 'barcode': '234567890124', 'cat': cat_dairy},
                {'name': 'Cheese Slices 200g', 'buying_price': 200, 'selling_price': 250, 'quantity': 20,
                 'unit': 'pack', 'barcode': '234567890125', 'cat': cat_dairy},
                {'name': 'Butter 250g', 'buying_price': 140, 'selling_price': 180, 'quantity': 30, 'unit': 'pack',
                 'barcode': '234567890126', 'cat': cat_dairy},
                # Snacks
                {'name': 'Potato Chips 80g', 'buying_price': 80, 'selling_price': 100, 'quantity': 80, 'unit': 'pack',
                 'barcode': '345678901234', 'cat': cat_snacks},
                {'name': 'Chocolate Bar', 'buying_price': 60, 'selling_price': 80, 'quantity': 60, 'unit': 'pcs',
                 'barcode': '345678901235', 'cat': cat_snacks},
                {'name': 'Biscuits 200g', 'buying_price': 90, 'selling_price': 120, 'quantity': 50, 'unit': 'pack',
                 'barcode': '345678901236', 'cat': cat_snacks},
                {'name': 'Peanuts 100g', 'buying_price': 45, 'selling_price': 60, 'quantity': 70, 'unit': 'pack',
                 'barcode': '345678901237', 'cat': cat_snacks},
                # Fruits
                {'name': 'Apple (1kg)', 'buying_price': 250, 'selling_price': 300, 'quantity': 40, 'unit': 'kg',
                 'barcode': '456789012345', 'cat': cat_fruits},
                {'name': 'Banana (1kg)', 'buying_price': 120, 'selling_price': 150, 'quantity': 50, 'unit': 'kg',
                 'barcode': '456789012346', 'cat': cat_fruits},
                {'name': 'Orange (1kg)', 'buying_price': 160, 'selling_price': 200, 'quantity': 45, 'unit': 'kg',
                 'barcode': '456789012347', 'cat': cat_fruits},
                # Vegetables
                {'name': 'Tomatoes (1kg)', 'buying_price': 90, 'selling_price': 120, 'quantity': 30, 'unit': 'kg',
                 'barcode': '567890123456', 'cat': cat_veg},
                {'name': 'Onions (1kg)', 'buying_price': 75, 'selling_price': 100, 'quantity': 40, 'unit': 'kg',
                 'barcode': '567890123457', 'cat': cat_veg},
                {'name': 'Potatoes (1kg)', 'buying_price': 60, 'selling_price': 80, 'quantity': 60, 'unit': 'kg',
                 'barcode': '567890123458', 'cat': cat_veg},
                # Household
                {'name': 'Laundry Detergent 500g', 'buying_price': 200, 'selling_price': 250, 'quantity': 25,
                 'unit': 'pack', 'barcode': '678901234567', 'cat': cat_household},
                {'name': 'Dish Soap 500ml', 'buying_price': 140, 'selling_price': 180, 'quantity': 35, 'unit': 'bottle',
                 'barcode': '678901234568', 'cat': cat_household},
                {'name': 'Toilet Paper 4 rolls', 'buying_price': 180, 'selling_price': 220, 'quantity': 40,
                 'unit': 'pack', 'barcode': '678901234569', 'cat': cat_household},
                {'name': 'All-Purpose Cleaner 1L', 'buying_price': 240, 'selling_price': 300, 'quantity': 20,
                 'unit': 'bottle', 'barcode': '678901234570', 'cat': cat_household},
                {'name': 'Sponge Set', 'buying_price': 70, 'selling_price': 90, 'quantity': 50, 'unit': 'pack',
                 'barcode': '678901234571', 'cat': cat_household},
                # Grains
                {'name': 'Rice 1kg', 'buying_price': 180, 'selling_price': 220, 'quantity': 80, 'unit': 'kg',
                 'barcode': '789012345678', 'cat': cat_grains},
                {'name': 'Sugar 1kg', 'buying_price': 140, 'selling_price': 180, 'quantity': 60, 'unit': 'kg',
                 'barcode': '789012345679', 'cat': cat_grains},
                {'name': 'Bread', 'buying_price': 40, 'selling_price': 50, 'quantity': 100, 'unit': 'loaf',
                 'barcode': '789012345680', 'cat': cat_grains},
                {'name': 'Millet 1kg', 'buying_price': 160, 'selling_price': 200, 'quantity': 30, 'unit': 'kg',
                 'barcode': '789012345681', 'cat': cat_grains},
            ]
            for p in sample_products:
                product = Product(
                    name=p['name'],
                    buying_price=p['buying_price'],
                    selling_price=p['selling_price'],
                    quantity_in_stock=p['quantity'],
                    unit=p['unit'],
                    barcode=p['barcode'],
                    category_id=p['cat'].id if p['cat'] else None
                )
                db.session.add(product)
            db.session.commit()

        if Supplier.query.count() == 0:
            suppliers = [
                Supplier(name='ABC Distributors', contact_person='John Doe', phone='0712345678', email='abc@mail.com',
                         address='Nairobi'),
                Supplier(name='XYZ Wholesalers', contact_person='Jane Smith', phone='0723456789', email='xyz@mail.com',
                         address='Mombasa')
            ]
            db.session.add_all(suppliers)
            db.session.commit()

        if LoyaltyCustomer.query.count() == 0:
            cust = LoyaltyCustomer(phone='0711111111', name='Loyal Customer', points=100, total_spent=5000)
            db.session.add(cust)
            db.session.commit()


# ---------------------------
# Initialize database
# ---------------------------
with app.app_context():
    db.create_all()
    add_missing_columns()
    seed_data()


# ========== ADDED FEATURES ==========
@app.route('/static/bootstrap/css/bootstrap.min.css')
def bootstrap_css():
    return send_from_directory('static/bootstrap/css', 'bootstrap.min.css')


@app.route('/static/bootstrap/js/bootstrap.bundle.min.js')
def bootstrap_js():
    return send_from_directory('static/bootstrap/js', 'bootstrap.bundle.min.js')


@app.route('/static/fontawesome/css/all.min.css')
def fontawesome_css():
    return send_from_directory('static/fontawesome/css', 'all.min.css')


@app.route('/static/fontawesome/webfonts/<path:filename>')
def fontawesome_webfonts(filename):
    return send_from_directory('static/fontawesome/webfonts', filename)


@app.route('/api/maintenance/status', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def maintenance_status():
    import sys, platform
    return jsonify({
        'status': 'operational',
        'python_version': sys.version,
        'platform': platform.platform(),
        'database': app.config['SQLALCHEMY_DATABASE_URI'],
        'instructions': 'If system crashes, restart with: python api.py (or use systemd). Contact developer for persistent issues.',
        'last_backup': 'Use the Backup button in the sidebar to create a manual backup.'
    })


@app.route('/api/reports/profit-analysis', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def profit_analysis():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    query = db.session.query(
        Product.id, Product.name, Product.buying_price, Product.selling_price,
        func.coalesce(func.sum(InvoiceItem.quantity), 0).label('total_qty'),
        func.coalesce(func.sum(InvoiceItem.total), 0).label('total_revenue')
    ).outerjoin(InvoiceItem, Product.id == InvoiceItem.product_id) \
        .outerjoin(Invoice, InvoiceItem.invoice_id == Invoice.id)
    if from_date:
        query = query.filter(Invoice.sale_date >= from_date)
    if to_date:
        query = query.filter(Invoice.sale_date <= to_date)
    results = query.group_by(Product.id).all()
    report = []
    for r in results:
        total_qty = int(r.total_qty)
        total_cost = float(r.buying_price) * total_qty
        total_revenue = float(r.total_revenue)
        profit = total_revenue - total_cost
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        report.append({
            'product_id': r.id,
            'name': r.name,
            'quantity_sold': total_qty,
            'total_revenue': round(total_revenue, 2),
            'total_cost': round(total_cost, 2),
            'profit': round(profit, 2),
            'profit_margin': round(margin, 2),
            'selling_price': float(r.selling_price),
            'buying_price': float(r.buying_price)
        })
    return jsonify(report)


@app.route('/api/reports/fast-moving', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def fast_moving_products():
    days = request.args.get('days', default=30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    subq = db.session.query(
        InvoiceItem.product_id,
        func.sum(InvoiceItem.quantity).label('total_qty')
    ).join(Invoice, InvoiceItem.invoice_id == Invoice.id) \
        .filter(Invoice.sale_date >= cutoff) \
        .group_by(InvoiceItem.product_id).subquery()
    results = db.session.query(
        Product.id, Product.name, Product.unit,
        func.coalesce(subq.c.total_qty, 0).label('total_qty'),
        func.count(func.distinct(func.date(Invoice.sale_date))).label('days_with_sales')
    ).outerjoin(subq, Product.id == subq.c.product_id) \
        .outerjoin(InvoiceItem, Product.id == InvoiceItem.product_id) \
        .outerjoin(Invoice, InvoiceItem.invoice_id == Invoice.id) \
        .filter((Invoice.sale_date >= cutoff) | (Invoice.sale_date.is_(None))) \
        .group_by(Product.id, subq.c.total_qty).all()
    report = []
    for r in results:
        total_qty = int(r.total_qty)
        days_with_sales = r.days_with_sales or 1
        avg_daily = total_qty / days_with_sales
        report.append({
            'product_id': r.id,
            'name': r.name,
            'unit': r.unit,
            'total_quantity_sold': total_qty,
            'days_with_sales': days_with_sales,
            'avg_daily_sales': round(avg_daily, 2)
        })
    report.sort(key=lambda x: x['avg_daily_sales'], reverse=True)
    return jsonify(report[:20])


@app.route('/api/reports/daily-top-products', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def daily_top_products():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    daily_sales = db.session.query(
        func.date(Invoice.sale_date).label('sale_date'),
        InvoiceItem.product_id,
        func.sum(InvoiceItem.quantity).label('qty_sold')
    ).join(Invoice, InvoiceItem.invoice_id == Invoice.id) \
        .group_by(func.date(Invoice.sale_date), InvoiceItem.product_id)
    if from_date:
        daily_sales = daily_sales.filter(Invoice.sale_date >= from_date)
    if to_date:
        daily_sales = daily_sales.filter(Invoice.sale_date <= to_date)
    daily_sales = daily_sales.subquery()
    ranked = db.session.query(
        daily_sales.c.sale_date,
        daily_sales.c.product_id,
        daily_sales.c.qty_sold,
        Product.name,
        Product.unit,
        db.func.row_number().over(
            partition_by=daily_sales.c.sale_date,
            order_by=daily_sales.c.qty_sold.desc()
        ).label('rank')
    ).join(Product, daily_sales.c.product_id == Product.id).subquery()
    top_per_day = db.session.query(ranked).filter(ranked.c.rank == 1).order_by(ranked.c.sale_date.desc()).all()
    result = []
    for row in top_per_day:
        # Safe date conversion
        if hasattr(row.sale_date, 'isoformat'):
            date_str = row.sale_date.isoformat()
        else:
            date_str = str(row.sale_date)
        result.append({
            'date': date_str,
            'product_id': row.product_id,
            'product_name': row.name,
            'quantity_sold': row.qty_sold,
            'unit': row.unit
        })
    return jsonify(result)


@app.route('/api/offline/data', methods=['GET'])
@token_required
def get_offline_data():
    products = Product.query.all()
    categories = Category.query.all()
    users = User.query.with_entities(User.id, User.username, User.full_name, User.role).all()
    settings = Setting.query.all()
    return jsonify({
        'products': [p.to_dict() for p in products],
        'categories': [c.to_dict() for c in categories],
        'users': [{'id': u.id, 'username': u.username, 'full_name': u.full_name, 'role': u.role} for u in users],
        'settings': [s.to_dict() for s in settings],
        'last_updated': datetime.utcnow().isoformat()
    })


@app.route('/api/sync/sales', methods=['POST'])
@token_required
def sync_sales():
    data = request.json
    offline_transactions = data.get('transactions', [])
    results = []
    for tx in offline_transactions:
        try:
            sale_data = tx.get('sale_data')
            if not sale_data:
                results.append({'id': tx.get('id'), 'status': 'error', 'message': 'Missing sale_data'})
                continue
            today = datetime.utcnow().strftime('%Y%m%d')
            last_inv = Invoice.query.filter(Invoice.invoice_no.like(f'INV-{today}-%')).order_by(
                Invoice.id.desc()).first()
            seq = int(last_inv.invoice_no.split('-')[-1]) + 1 if last_inv else 1
            invoice_no = f"INV-{today}-{seq:04d}"
            active_shift = Shift.query.filter_by(user_id=g.current_user.id, status='active').first()
            cashier_display = active_shift.shift_display_name if active_shift and active_shift.shift_display_name else g.current_user.full_name
            invoice = Invoice(
                invoice_no=invoice_no,
                customer_name=sale_data.get('customer_name'),
                customer_phone=sale_data.get('customer_phone'),
                subtotal=sale_data['subtotal'],
                discount=sale_data.get('discount', 0),
                tax=sale_data.get('tax', 0),
                total=sale_data['total'],
                payment_method=sale_data.get('payment_method', 'Cash'),
                cashier_id=g.current_user.id,
                cashier_display_name=cashier_display
            )
            db.session.add(invoice)
            db.session.flush()
            for item_data in sale_data['items']:
                product = Product.query.get(item_data['product_id'])
                if not product:
                    raise ValueError(f"Product {item_data['product_id']} not found")
                if product.quantity_in_stock < item_data['quantity']:
                    raise ValueError(f"Insufficient stock for {product.name}")
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
            log_action(g.current_user.id, 'sale', f"Invoice {invoice_no} total {invoice.total} (synced offline)")
            results.append({'id': tx.get('id'), 'status': 'success', 'invoice': invoice.to_dict()})
        except Exception as e:
            db.session.rollback()
            results.append({'id': tx.get('id'), 'status': 'error', 'message': str(e)})
    return jsonify({'results': results})


@app.route('/api/audit_logs', methods=['GET'])
@token_required
@role_required(['admin', 'manager'])
def get_audit_logs():
    limit = request.args.get('limit', 200, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify([log.to_dict() for log in logs])


@app.route('/api/reports/product-profit', methods=['GET'])
@token_required
@role_required(['admin', 'manager', 'cashier'])
def product_profit_report():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    query = db.session.query(
        Product.id, Product.name, Product.buying_price, Product.selling_price,
        func.coalesce(func.sum(InvoiceItem.quantity), 0).label('qty_sold'),
        func.coalesce(func.sum(InvoiceItem.total), 0).label('revenue')
    ).outerjoin(InvoiceItem, Product.id == InvoiceItem.product_id) \
        .outerjoin(Invoice, InvoiceItem.invoice_id == Invoice.id)
    if from_date:
        query = query.filter(Invoice.sale_date >= from_date)
    if to_date:
        query = query.filter(Invoice.sale_date <= to_date)
    results = query.group_by(Product.id).all()
    report = []
    for r in results:
        qty = int(r.qty_sold)
        cost_total = float(r.buying_price) * qty
        revenue_total = float(r.revenue)
        profit = revenue_total - cost_total
        report.append({
            'product_id': r.id,
            'name': r.name,
            'buying_price': float(r.buying_price),
            'selling_price': float(r.selling_price),
            'quantity_sold': qty,
            'total_cost': round(cost_total, 2),
            'total_revenue': round(revenue_total, 2),
            'profit': round(profit, 2)
        })
    return jsonify(report)


@app.route('/api/reports/daily-profit-loss', methods=['GET'])
@token_required
@role_required(['admin', 'manager', 'cashier'])
def daily_profit_loss():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    cost_subq = db.session.query(
        InvoiceItem.invoice_id,
        func.sum(cast(Product.buying_price, Numeric(10, 2)) * InvoiceItem.quantity).label('total_cost')
    ).join(Product, InvoiceItem.product_id == Product.id) \
        .group_by(InvoiceItem.invoice_id).subquery()
    query = db.session.query(
        func.date(Invoice.sale_date).label('date'),
        func.sum(Invoice.total).label('revenue'),
        func.coalesce(func.sum(cost_subq.c.total_cost), 0).label('cost')
    ).outerjoin(cost_subq, Invoice.id == cost_subq.c.invoice_id) \
        .group_by(func.date(Invoice.sale_date))
    if from_date:
        query = query.filter(Invoice.sale_date >= from_date)
    if to_date:
        query = query.filter(Invoice.sale_date <= to_date)
    results = query.order_by(func.date(Invoice.sale_date).desc()).all()
    daily_report = []
    for r in results:
        revenue = float(r.revenue) if r.revenue else 0
        cost = float(r.cost) if r.cost else 0
        profit = revenue - cost
        # Convert date safely (SQLite returns string, PostgreSQL returns date)
        if hasattr(r.date, 'isoformat'):
            date_str = r.date.isoformat()
        else:
            date_str = str(r.date)
        daily_report.append({
            'date': date_str,
            'total_cost': round(cost, 2),
            'total_revenue': round(revenue, 2),
            'profit': round(profit, 2)
        })
    return jsonify(daily_report)


# ---------------------------
# Run app
# ---------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') == 'development')