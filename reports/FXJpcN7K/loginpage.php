<?php
include '../config/brands.php'; // Connection file
$brand_campaign_id = 'FXJpcN7K';

$correct_username = "Wallace Pharmaceuticals";
$correct_password = "password123";

// Check if form is submitted
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $username = $_POST["username"];
    $password = $_POST["password"];

    // Validate username and password
    if ($username === $correct_username && $password === $correct_password) {
        // Simulate loading with sleep (2 seconds)
        sleep(2);

        // Redirect after successful login
        // Make sure the brand_campaign_id is retrieved from the database if necessary
        $redirect_url = "https://reports.cpdinclinic.co.in/reports/$brand_campaign_id/$brand_campaign_id/index.php?brand_campaign_id=" . htmlspecialchars($brand_campaign_id);
        header("Location: $redirect_url");
        exit();
    } else {
        // If login fails, redirect back to the login page with error
        header("Location: loginpage.php?error=1");
        exit();
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login Page</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f0f0f0;
        }

        .login-container {
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.1);
            width: 320px;
            text-align: center;
        }

        .login-container h2 {
            font-size: 24px;
            margin-bottom: 20px;
            color: #333;
        }

        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border-radius: 5px;
            border: 1px solid #ccc;
            box-sizing: border-box;
            font-size: 16px;
        }

        button {
            width: 100%;
            padding: 12px;
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }

        button:hover {
            background-color: #218838;
        }

        .loading-bar {
            display: none;
            height: 5px;
            background-color: #28a745;
            margin-top: 20px;
            animation: loading 2s infinite;
        }

        @keyframes loading {
            0% {
                width: 0;
            }
            100% {
                width: 100%;
            }
        }

        .loading-message {
            text-align: center;
            color: #28a745;
            margin-top: 10px;
            display: none;
            font-size: 14px;
        }

        /* Error message style */
        .error-message {
            color: red;
            font-size: 14px;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>

<div class="login-container">
    <h2>Login</h2>
    
    <?php
    // Show error message if there's an error in login
    if (isset($_GET['error']) && $_GET['error'] == 1) {
        echo "<div class='error-message'>Invalid username or password</div>";
    }
    ?>

    <form id="loginForm" action="" method="POST">
        <input type="text" name="username" placeholder="Username" required>
        <input type="password" name="password" placeholder="Password" required>
        <button type="submit">Login</button>
    </form>

    <div class="loading-bar" id="loadingBar"></div>
    <div class="loading-message" id="loadingMessage">Logging you in...</div>
</div>

<script>
    const form = document.getElementById('loginForm');
    const loadingBar = document.getElementById('loadingBar');
    const loadingMessage = document.getElementById('loadingMessage');

    // Reset the loading bar when the page is loaded
    window.addEventListener('pageshow', function () {
        loadingBar.style.display = 'none';
        loadingMessage.style.display = 'none';
    });

    form.addEventListener('submit', function () {
        // Display loading bar and message when form is submitted
        loadingBar.style.display = 'block';
        loadingMessage.style.display = 'block';
    });
</script>

</body>
</html>
