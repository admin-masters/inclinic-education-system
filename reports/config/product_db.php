<?php
// server/db.php

function createConnection($servername, $username, $password, $dbname) {
    $conn = new mysqli($servername, $username, $password, $dbname);
    if ($conn->connect_error) {
        error_log("Connection failed: " . $conn->connect_error);
        die("Connection failed.");
    }
    return $conn;
}

$product_conn = createConnection("35.154.143.170", "test_mha_u", "7NVP4MvUXdbVJNYQ9UEy", "test_mha");


?>

