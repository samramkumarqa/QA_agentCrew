# Business Requirements Document: Swag Labs Web Shop (Release 2.5)

## 1. Purpose
Swag Labs sells branded merchandise online. This release covers login, the product catalogue, the
shopping cart and checkout for registered customers. Payment is simulated; no real card is charged.

## 2. Users
- **Customer**: a registered user who browses and buys products.
- **Locked customer**: an account blocked by the support team.

## 3. Functional requirements

### 3.1 Login
- Customers log in with a username and password on the login page.
- After a successful login the Products page is shown.
- If the username or password is wrong, the page shows: "Epic sadface: Username and password do not match any user in this service".
- A locked customer cannot log in and sees: "Epic sadface: Sorry, this user has been locked out."
- Both fields are required. Submitting with an empty username shows "Epic sadface: Username is required".
- The session ends after a period of inactivity.

### 3.2 Product catalogue
- The Products page lists all six products with name, description, price and an "Add to cart" button.
- Customers can sort the list by Name (A to Z), Name (Z to A), Price (low to high) and Price (high to low). The default sort is Name (A to Z).
- Clicking a product name opens its details page with a "Back to products" button.

### 3.3 Shopping cart
- "Add to cart" adds one unit of the product and changes the button to "Remove".
- The cart icon shows a badge with the number of items in the cart. With an empty cart no badge is shown.
- The cart page lists each item with quantity, name, description and price, and has "Continue Shopping" and "Checkout" buttons.
- Items can be removed from the cart page or the Products page; the badge updates immediately.
- The cart is kept when the customer navigates between pages during the session.

### 3.4 Checkout
- Step 1 asks for First Name, Last Name and Zip/Postal Code. All three are required. Missing fields show, in this order of checking:
  "Error: First Name is required", "Error: Last Name is required", "Error: Postal Code is required".
- Step 2 (Overview) shows the items, the payment and shipping information, the item total, tax and the total.
- Tax is 8% of the item total.
- "Finish" completes the order and shows "Thank you for your order!". The cart is then empty.
- "Cancel" on step 1 returns to the cart; on step 2 it returns to the Products page.

### 3.5 Menu
- The side menu has All Items, About, Logout and Reset App State.
- Logout returns to the login page. After logout, protected pages cannot be opened without logging in again.
- Reset App State empties the cart and resets all "Remove" buttons to "Add to cart".

## 4. Non-functional requirements
- Pages load within 3 seconds on a standard broadband connection.
- The shop works on the latest versions of Chrome, Firefox and Safari.

## 5. Out of scope
Real payments, order history, user registration and password reset.
