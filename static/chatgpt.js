$(document).ready(function() {
    var $chatBox = $("#chatBox");
    var $text2 = $("#text2");

    $("#messageArea2").submit(function(e) {
        e.preventDefault();
        sendMessage();
    });

    $('#chatbotName').click(function() {
        var newName = prompt("Please enter a new name for the chatbot:");
        if (newName) {
            $(this).text(newName);
        }
    });

    function sendMessage() {
        var userInput = $text2.val().trim();
        if (!userInput) return;

        console.log("Sending message:", userInput);

        var str_time = getCurrentTimeString();
        var userHtml = '<div class="d-flex justify-content-end mb-4"><div class="msg_cotainer_send">' + escapeHtml(userInput) + '<span class="msg_time_send">' + str_time + '</span></div></div>';
        $chatBox.append(userHtml);
        $text2.val('');

        $.ajax({
            url: '/gpt',
            type: 'POST',
            contentType: 'application/x-www-form-urlencoded',
            data: {user_message: userInput},
            dataType: 'json',
            success: function(data) {
                if (data.assistant_message) {
                    var response = formatResponse(data.assistant_message);
                    var botHtml = '<div class="d-flex justify-content-start mb-4"><div class="msg_cotainer">' + response + '<span class="msg_time">' + str_time + '</span></div></div>';
                    $chatBox.append(botHtml);
                    $chatBox.scrollTop($chatBox[0].scrollHeight);
                } else {
                    console.error("Invalid format in response:", data);
                    appendErrorMessage("Received an invalid response format.");
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error('AJAX request failed:', textStatus, errorThrown, jqXHR);
                appendErrorMessage("Sorry, there was an error processing your request. Please try again later.");
            }
        });
    }

    function formatResponse(response) {
        return response.replace(/\n/g, "<br>");
    }

    function getCurrentTimeString() {
        var date = new Date();
        return date.getHours() + ":" + date.getMinutes().toString().padStart(2, '0');
    }

    function appendErrorMessage(message) {
        var errorMsg = '<div class="d-flex justify-content-start mb-4"><div class="msg_cotainer">' + message + '<span class="msg_time">' + getCurrentTimeString() + '</span></div></div>';
        $chatBox.append(errorMsg);
    }

    function escapeHtml(text) {
        return text.replace(/&/g, "&amp;")
                   .replace(/</g, "&lt;")
                   .replace(/>/g, "&gt;")
                   .replace(/"/g, "&quot;")
                   .replace(/'/g, "&#039;");
    }
});
