BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "categories" (
	"id"	INTEGER NOT NULL,
	"name"	VARCHAR(100) NOT NULL,
	"description"	TEXT,
	PRIMARY KEY("id"),
	UNIQUE("name")
);
CREATE TABLE IF NOT EXISTS "expenses" (
	"id"	INTEGER NOT NULL,
	"category"	VARCHAR(100) NOT NULL,
	"amount"	NUMERIC(10, 2) NOT NULL,
	"description"	TEXT,
	"expense_date"	DATE,
	"user_id"	INTEGER,
	"created_at"	DATETIME,
	PRIMARY KEY("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "invoice_items" (
	"id"	INTEGER NOT NULL,
	"invoice_id"	INTEGER,
	"product_id"	INTEGER,
	"product_name"	VARCHAR(200),
	"quantity"	INTEGER NOT NULL,
	"unit_price"	NUMERIC(10, 2) NOT NULL,
	"total"	NUMERIC(10, 2) NOT NULL,
	PRIMARY KEY("id"),
	FOREIGN KEY("invoice_id") REFERENCES "invoices"("id"),
	FOREIGN KEY("product_id") REFERENCES "products"("id")
);
CREATE TABLE IF NOT EXISTS "invoices" (
	"id"	INTEGER NOT NULL,
	"invoice_no"	VARCHAR(50) NOT NULL,
	"customer_name"	VARCHAR(100),
	"customer_phone"	VARCHAR(20),
	"subtotal"	NUMERIC(10, 2),
	"discount"	NUMERIC(10, 2),
	"tax"	NUMERIC(10, 2),
	"total"	NUMERIC(10, 2) NOT NULL,
	"payment_method"	VARCHAR(50),
	"cashier_id"	INTEGER,
	"sale_date"	DATETIME,
	"cashier_display_name"	VARCHAR(100),
	PRIMARY KEY("id"),
	UNIQUE("invoice_no"),
	FOREIGN KEY("cashier_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "loyalty_customers" (
	"phone"	VARCHAR(20) NOT NULL,
	"name"	VARCHAR(100) NOT NULL,
	"points"	INTEGER,
	"total_spent"	NUMERIC(10, 2),
	"tier"	VARCHAR(20),
	"joined_date"	DATETIME,
	PRIMARY KEY("phone")
);
CREATE TABLE IF NOT EXISTS "products" (
	"id"	INTEGER NOT NULL,
	"barcode"	VARCHAR(50),
	"name"	VARCHAR(200) NOT NULL,
	"category_id"	INTEGER,
	"buying_price"	NUMERIC(10, 2),
	"selling_price"	NUMERIC(10, 2) NOT NULL,
	"quantity_in_stock"	INTEGER,
	"min_stock"	INTEGER,
	"unit"	VARCHAR(20),
	"supplier"	VARCHAR(200),
	"created_at"	DATETIME,
	UNIQUE("barcode"),
	PRIMARY KEY("id"),
	FOREIGN KEY("category_id") REFERENCES "categories"("id")
);
CREATE TABLE IF NOT EXISTS "returns" (
	"id"	INTEGER NOT NULL,
	"original_invoice"	VARCHAR(50) NOT NULL,
	"return_invoice"	VARCHAR(50) NOT NULL,
	"product_id"	INTEGER,
	"product_name"	VARCHAR(200),
	"quantity"	INTEGER NOT NULL,
	"refund_amount"	NUMERIC(10, 2) NOT NULL,
	"reason"	VARCHAR(200),
	"cashier_id"	INTEGER,
	"return_date"	DATETIME,
	PRIMARY KEY("id"),
	UNIQUE("return_invoice"),
	FOREIGN KEY("cashier_id") REFERENCES "users"("id"),
	FOREIGN KEY("product_id") REFERENCES "products"("id")
);
CREATE TABLE IF NOT EXISTS "settings" (
	"key"	VARCHAR(100) NOT NULL,
	"value"	TEXT,
	PRIMARY KEY("key")
);
CREATE TABLE IF NOT EXISTS "shifts" (
	"id"	INTEGER NOT NULL,
	"user_id"	INTEGER,
	"start_time"	DATETIME,
	"end_time"	DATETIME,
	"total_sales"	NUMERIC(10, 2),
	"status"	VARCHAR(20),
	"shift_display_name"	VARCHAR(100),
	PRIMARY KEY("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "stock_movements" (
	"id"	INTEGER NOT NULL,
	"product_id"	INTEGER,
	"movement_type"	VARCHAR(20),
	"quantity"	INTEGER NOT NULL,
	"reason"	VARCHAR(200),
	"user_id"	INTEGER,
	"created_at"	DATETIME,
	PRIMARY KEY("id"),
	FOREIGN KEY("product_id") REFERENCES "products"("id"),
	FOREIGN KEY("user_id") REFERENCES "users"("id")
);
CREATE TABLE IF NOT EXISTS "suppliers" (
	"id"	INTEGER NOT NULL,
	"name"	VARCHAR(100) NOT NULL,
	"contact_person"	VARCHAR(100),
	"phone"	VARCHAR(20),
	"email"	VARCHAR(100),
	"address"	TEXT,
	"created_at"	DATETIME,
	PRIMARY KEY("id")
);
CREATE TABLE IF NOT EXISTS "users" (
	"id"	INTEGER NOT NULL,
	"username"	VARCHAR(80) NOT NULL,
	"password_hash"	VARCHAR(200) NOT NULL,
	"role"	VARCHAR(20),
	"full_name"	VARCHAR(100) NOT NULL,
	"created_at"	DATETIME,
	PRIMARY KEY("id"),
	UNIQUE("username")
);
INSERT INTO "categories" VALUES (1,'Beverages',NULL);
INSERT INTO "categories" VALUES (2,'Snacks',NULL);
INSERT INTO "categories" VALUES (3,'Dairy',NULL);
INSERT INTO "categories" VALUES (4,'Fruits',NULL);
INSERT INTO "categories" VALUES (5,'Vegetables',NULL);
INSERT INTO "categories" VALUES (6,'Household',NULL);
INSERT INTO "loyalty_customers" VALUES ('0711111111','Loyal Customer',100,5000,'Bronze','2026-06-05 13:27:53.673269');
INSERT INTO "products" VALUES (1,'123456789012','Coca Cola 500ml',1,0,120,50,5,'bottle',NULL,'2026-06-05 13:27:53.644931');
INSERT INTO "products" VALUES (2,'123456789013','Pepsi 500ml',1,0,120,45,5,'bottle',NULL,'2026-06-05 13:27:53.644935');
INSERT INTO "products" VALUES (3,'123456789014','Fanta Orange 500ml',1,0,120,40,5,'bottle',NULL,'2026-06-05 13:27:53.644937');
INSERT INTO "products" VALUES (4,'123456789015','Sprite 500ml',1,0,120,40,5,'bottle',NULL,'2026-06-05 13:27:53.644939');
INSERT INTO "products" VALUES (5,'123456789016','Minute Maid Juice 1L',1,0,200,30,5,'carton',NULL,'2026-06-05 13:27:53.644941');
INSERT INTO "products" VALUES (6,'234567890123','Fresh Milk 1L',3,0,85,30,5,'carton',NULL,'2026-06-05 13:27:53.644942');
INSERT INTO "products" VALUES (7,'234567890124','Yogurt 500ml',3,0,70,25,5,'cup',NULL,'2026-06-05 13:27:53.644944');
INSERT INTO "products" VALUES (8,'234567890125','Cheese Slices 200g',3,0,250,20,5,'pack',NULL,'2026-06-05 13:27:53.644946');
INSERT INTO "products" VALUES (9,'234567890126','Butter 250g',3,0,180,30,5,'pack',NULL,'2026-06-05 13:27:53.644947');
INSERT INTO "products" VALUES (10,'345678901234','Potato Chips 80g',2,0,100,80,5,'pack',NULL,'2026-06-05 13:27:53.644949');
INSERT INTO "products" VALUES (11,'345678901235','Chocolate Bar',2,0,80,60,5,'pcs',NULL,'2026-06-05 13:27:53.644951');
INSERT INTO "products" VALUES (12,'345678901236','Biscuits 200g',2,0,120,50,5,'pack',NULL,'2026-06-05 13:27:53.644952');
INSERT INTO "products" VALUES (13,'345678901237','Peanuts 100g',2,0,60,70,5,'pack',NULL,'2026-06-05 13:27:53.644954');
INSERT INTO "products" VALUES (14,'456789012345','Apple (1kg)',4,0,300,40,5,'kg',NULL,'2026-06-05 13:27:53.644956');
INSERT INTO "products" VALUES (15,'456789012346','Banana (1kg)',4,0,150,50,5,'kg',NULL,'2026-06-05 13:27:53.644957');
INSERT INTO "products" VALUES (16,'456789012347','Orange (1kg)',4,0,200,45,5,'kg',NULL,'2026-06-05 13:27:53.644959');
INSERT INTO "products" VALUES (17,'567890123456','Tomatoes (1kg)',5,0,120,30,5,'kg',NULL,'2026-06-05 13:27:53.644961');
INSERT INTO "products" VALUES (18,'567890123457','Onions (1kg)',5,0,100,40,5,'kg',NULL,'2026-06-05 13:27:53.644962');
INSERT INTO "products" VALUES (19,'567890123458','Potatoes (1kg)',5,0,80,60,5,'kg',NULL,'2026-06-05 13:27:53.644964');
INSERT INTO "products" VALUES (20,'678901234567','Laundry Detergent 500g',6,0,250,25,5,'pack',NULL,'2026-06-05 13:27:53.644966');
INSERT INTO "products" VALUES (21,'678901234568','Dish Soap 500ml',6,0,180,35,5,'bottle',NULL,'2026-06-05 13:27:53.644967');
INSERT INTO "products" VALUES (22,'678901234569','Toilet Paper 4 rolls',6,0,220,40,5,'pack',NULL,'2026-06-05 13:27:53.644969');
INSERT INTO "products" VALUES (23,'678901234570','All-Purpose Cleaner 1L',6,0,300,20,5,'bottle',NULL,'2026-06-05 13:27:53.644971');
INSERT INTO "products" VALUES (24,'678901234571','Sponge Set',6,0,90,50,5,'pack',NULL,'2026-06-05 13:27:53.644973');
INSERT INTO "suppliers" VALUES (1,'ABC Distributors','John Doe','0712345678','abc@mail.com','Nairobi','2026-06-05 13:27:53.660066');
INSERT INTO "suppliers" VALUES (2,'XYZ Wholesalers','Jane Smith','0723456789','xyz@mail.com','Mombasa','2026-06-05 13:27:53.660069');
INSERT INTO "users" VALUES (1,'manuel','scrypt:32768:8:1$olMtwX2Ji6XWW9Pb$d20307cae44714f1f27855cb67cec54a3c0bedf8089ab23562c7fb3ab764ceba56ebb601656518ec125326fc3a7a419965cb1384edabb05917086bb67dd12c49','admin','Administrator','2026-06-05 13:27:53.607734');
INSERT INTO "users" VALUES (2,'cashier','scrypt:32768:8:1$EFbfi1XMiGtNPl6i$76be35a5fd70490db011866ec2ee4b88cd2af2f76404fdef08d740c987dfc571060e1e6b862bd6790247ea624aab725072b5fd191c82fd494715f03979130e5c','cashier','Cashier User','2026-06-05 13:27:53.607739');
COMMIT;
