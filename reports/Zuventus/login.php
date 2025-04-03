<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login Page</title>
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    <style>
        body {
            background-color: #f8f9fa;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            font-family: Arial, sans-serif;
        }

        .login-container {
            max-width: 500px;
            width: 100%;
            padding: 20px;
            background-color: #ffffff;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }

        .login-container h2 {
            text-align: center;
            margin-bottom: 20px;
            color: #387478;
        }

        .btn-primary {
            background-color: #387478;
            border: none;
        }

        .btn-primary:hover {
            background-color: #243642;
        }

        .error-message {
            color: red;
            font-size: 0.9em;
            text-align: center;
        }

        .password-container {
            position: relative;
        }

        .toggle-password {
            position: absolute;
            top: 70%;
            right: 10px;
            transform: translateY(-50%);
            cursor: pointer;
            color: #387478;
        }
    </style>
</head>

<body>
    <div class="login-container">
        <h2>Login</h2>

        <?php
        $predefined_email = "admin"; // Predefined username
        $predefined_password = "admin"; // Predefined password
        $error_message = "";

        if ($_SERVER["REQUEST_METHOD"] == "POST") {
            $email = $_POST["text"]; // Fetch username from the 'text' input
            $password = $_POST["password"]; // Fetch password

            if ($email === $predefined_email && $password === $predefined_password) {
                header("Location: https://reports.cpdinclinic.co.in/reports/Zuventus/dashboard.php");
                exit();
            } else {
                $error_message = "Invalid username or password.";
            }
        }
        ?>

        <?php if ($error_message): ?>
            <p class="error-message"><?php echo $error_message; ?></p>
        <?php endif; ?>

        <form method="POST" action="">
            <div class="form-group">
                <label for="text">Username (Gmail ID)</label>
                <input type="text" class="form-control" id="text" name="text" placeholder="Enter your Username" required>
            </div>
            <div class="form-group password-container">
                <label for="password">Password</label>
                <input type="password" class="form-control" id="password" name="password" placeholder="Enter your password" required>
                <i class="fas fa-eye toggle-password" onclick="togglePassword()"></i>
            </div>
            <button type="submit" class="btn btn-primary btn-block">Login</button>
        </form>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.0.7/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
    <script>
        function togglePassword() {
            const passwordInput = document.getElementById("password");
            const toggleIcon = document.querySelector(".toggle-password");

            if (passwordInput.type === "password") {
                passwordInput.type = "text";
                toggleIcon.classList.remove("fa-eye");
                toggleIcon.classList.add("fa-eye-slash");
            } else {
                passwordInput.type = "password";
                toggleIcon.classList.remove("fa-eye-slash");
                toggleIcon.classList.add("fa-eye");
            }
        }
    </script>
</body>

</html>