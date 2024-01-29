var threadId = null;
var instructions = "";

$(document).ready(function(){
    fetchBotName();
    fetchInitialData();
    setupEventListeners();
    loadChatHistory();
});

function fetchBotName() {
    $.get("/get_bot_name", function(response) {
        if (response.botName) {
            $("#chatbotName").text(response.botName);
        }
    }).fail(function() {
        console.error("Error fetching bot name");
    });
}

function fetchInitialData() {
    $.get("/start", function(data) {
        threadId = data.thread_id;
        console.log("Conversation started with thread ID: " + threadId);
        sendStartMessage();
    });

    $.get("/get_instructions", function(response) {
        instructions = response.instructions || "None";
    });

    $.get("/knowledge", function(data) {
        populateKnowledgeFiles(data);
    });
}

function setupEventListeners() {
    $("#send").click(handleSendMessage);
    $(document).on('click', '.delete', handleDeleteFile);
    $('#submitButton').click(handleSubmitInstructions);
    $('#add-knowledge').click(handleAddKnowledge);
    $('#chatbotName').click(showInstructions);
    $('#botName, #instructions').keypress(handleEnterPress);
}

function loadChatHistory() {
    $.get("/chat_history", function(data){
        var reversedChatHistory = data.chat_history.reverse();
        appendChatHistory(reversedChatHistory);
    });
}

function sendStartMessage() {
    var startMessage = "Hello, how can I assist you today?";
    var startHtml = createMessageHtml(startMessage, "assistant");
    $("#messageFormeight").append(startHtml);
}

function handleSendMessage(e) {
    e.preventDefault();
    var userInput = $("#text").val().trim();

    if (userInput === '/clear') {
        clearChat();
    } else {
        sendMessageToServer(userInput);
    }
}

function clearChat() {
    $.post('/clear_chat', function() {
        $("#messageFormeight").empty();
        sendStartMessage();
        $("#text").val('');
    });
}

function sendMessageToServer(userInput) {
    var userHtml = createMessageHtml(userInput, "user");
    $("#messageFormeight").append(userHtml);
    $("#text").val('');

    $.ajax({
        url: '/chat',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({thread_id: threadId, message: userInput}),
        dataType: 'json',
        success: function(data) {
            var formattedResponse = formatResponse(data.response);
            var responseHtml = createMessageHtml(formattedResponse, "assistant");
            $("#messageFormeight").append(responseHtml);
            scrollToBottom();
        },
        error: handleAjaxError
    });
}

function formatResponse(response) {
    // Remove the citation pattern like &#8203;``【oaicite:1】``&#8203;
    response = response.replace(/【\d+†source】/g, '');

    // Replace newline characters with <br> tags for HTML formatting
    response = response.replace(/\n/g, "<br>");

    return response;
}

function createMessageHtml(message, role) {
    var strTime = getCurrentTimeString();
    var messageClass = (role === "user") ? "msg_cotainer_send" : "msg_cotainer";
    var imgSrc = (role === "user") ? "https://i.ibb.co/d5b84Xw/Untitled-design.png" : "https://i.ibb.co/fSNP7Rz/icons8-chatgpt-512.png";
    var justifyClass = (role === "user") ? "justify-content-end" : "justify-content-start";

    return '<div class="d-flex ' + justifyClass + ' mb-4"><div class="' + messageClass + '">' + 
           message + '<span class="msg_time">' + strTime + '</span></div><div class="img_cont_msg">' +
           '<img src="' + imgSrc + '" class="rounded-circle user_img_msg"></div></div>';
}

function handleDeleteFile() {
    var filename = $(this).data('filename');
    var username = $(this).data('username');

    $.ajax({
        url: '/knowledge/' + username + '/' + filename,
        type: 'DELETE',
        success: function() {
            $(this).parent().remove();
        }
    });
}

function handleSubmitInstructions(e) {
    e.preventDefault();
    var botName = $("#botName").val();
    instructions = $("#instructions").val();

    $.ajax({
        url: '/submit_instructions',
        type: 'POST',
        data: {botName: botName, instructions: instructions},
        success: function(response) {
            console.log("Assistant ID: " + response.assistant_id);
        }
    });
}

function handleAddKnowledge() {
    var input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = function(event) {
        uploadFiles(event.target.files);
    };
    input.click();
}

function uploadFiles(files) {
    var formData = new FormData();
    for (var i = 0; i < files.length; i++) {
        if (validateFileExtension(files[i].name)) {
            formData.append('file', files[i]);
        } else {
            alert('This file type is not allowed.');
            return;
        }
    }
    $.ajax({
        url: '/knowledge',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function() {
            appendFilesToSidebar(files);
        }
    });
}

function validateFileExtension(filename) {
    var allowedExtensions = ['txt', 'json', 'c', 'cpp', 'docx', 'html', 'java', 'md', 'pdf', 'php', 'pptx', 'py', 'rb', 'tex'];
    var fileExtension = filename.split('.').pop();
    return allowedExtensions.includes(fileExtension);
}

function appendFilesToSidebar(files) {
    for (var i = 0; i < files.length; i++) {
        var fileHtml = "<p id='" + files[i].name + "'>" + files[i].name +
                       " <button class='delete btn-delete' data-filename='" + files[i].name + "'>x</button></p>";
        $("#knowledge").append(fileHtml);
    }
}

function showInstructions() {
    alert(instructions);
}

function handleEnterPress(e) {
    if (e.keyCode == 13 && !e.shiftKey) {
        e.preventDefault();
        $('#submitButton').click();
    }
}

function handleAjaxError(jqXHR) {
    var errorMsg = jqXHR.responseJSON && jqXHR.responseJSON.error ? jqXHR.responseJSON.error : "An error occurred";
    var errorHtml = createMessageHtml(errorMsg, "assistant");
    $("#messageFormeight").append(errorHtml);
}

function getCurrentTimeString() {
    var date = new Date();
    var hour = date.getHours();
    var minute = date.getMinutes().toString().padStart(2, '0');
    return hour + ":" + minute;
}

function scrollToBottom() {
    $('#messageFormeight').scrollTop($('#messageFormeight')[0].scrollHeight);
}

function populateKnowledgeFiles(data) {
    data.forEach(function(file) {
        var fileHtml = "<p id='" + file.filename + "'>" + file.filename +
                       " <button class='delete btn-delete' data-username='" + 
                       file.username + "' data-filename='" + file.filename + "'>x</button></p>";
        $("#knowledge").append(fileHtml);
    });
}

function appendChatHistory(chatHistory) {
    chatHistory.forEach(function(message) {
        var formattedMessage = formatResponse(message.content);
        var messageHtml = createMessageHtml(formattedMessage, message.role);
        $("#messageFormeight").append(messageHtml);
    });
    scrollToBottom();
}