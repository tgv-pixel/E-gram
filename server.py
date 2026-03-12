@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    try:
        # Format phone number
        if not phone.startswith('+'):
            phone = '+' + phone
        
        # Create event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create temporary client
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        # Send code request
        result = loop.run_until_complete(client.send_code_request(phone))
        
        # Store session
        session_id = hashlib.md5(f"{phone}_{time.time()}".encode()).hexdigest()
        temp_sessions[session_id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'created': time.time(),
            'loop': loop
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Code sent successfully'
        })
        
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        if 'client' in locals():
            try:
                loop.run_until_complete(client.disconnect())
            except:
                pass
        if 'loop' in locals():
            loop.close()
        return jsonify({'success': False, 'error': str(e)})
