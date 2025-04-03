<?php
$cpd = "cpdinclinic.co.in";
$formstage = "formsclone";



$dbHost = "localhost";
$dbUsername = "root";
$dbPassword = "7NVP4MvUXdbVJNYQ9UEy";
$dbName = "reports";

$captcha_key = "6Le5fe4nAAAAAG61E-T-__0ewohX4z1RhJYsL_O8";


$form_db = mysqli_connect($dbHost, $dbUsername, $dbPassword, $dbName);
mysqli_set_charset($form_db, 'utf8');
$db_select = mysqli_select_db($form_db, $dbName) or die(mysqli_error($form_db));

// $dbHost1 = "3.6.109.229";
// $dbUsername1 = "screeningappuser";
// $dbPassword1 = "PeNKaZ2lpTuwGUP8";
// $dbName1 = "product2.0";

// $captcha_key = "6Le5fe4nAAAAAG61E-T-__0ewohX4z1RhJYsL_O8";


// $form_db1 = mysqli_connect($dbHost1, $dbUsername1, $dbPassword1, $dbName1);
// mysqli_set_charset($form_db1, 'utf8');
// $db_select1 = mysqli_select_db($form_db1, $dbName1) or die(mysqli_error($form_db1));
